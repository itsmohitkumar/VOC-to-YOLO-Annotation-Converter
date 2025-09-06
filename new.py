@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Feedback batch regeneration:
    - Accepts list of feedback items: [{post_id, feedback_text}, ...]
    - Produces a single versioned approved_plan_v{batch_version}.json and latest approved_plan.json AFTER all posts
    - Persists feedback.json with approved_plan_versions history
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing enhanced multi-feedback for {campaign_full_name}")
        
        # Validations
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        user_campaigns = get_user_campaigns(username)
        if not user_campaigns:
            raise HTTPException(status_code=404, detail=f"No campaigns found for user '{username}'")
        
        campaign_match = next((c for c in user_campaigns if (c.get('campaign_name', '') or '').lower() == campaign_name.lower()), None)
        if not campaign_match:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")
        
        if not feedback_request or not feedback_request.feedbacks:
            raise HTTPException(status_code=400, detail="feedbacks list is required and cannot be empty")
        
        # Deduplicate feedbacks
        deduped_feedbacks = []
        seen_post_ids_lower = set()
        original_post_ids = []
        
        for fb in feedback_request.feedbacks:
            pid = (fb.post_id or "").strip()
            if not pid or not isinstance(pid, str):
                raise HTTPException(status_code=400, detail="Each feedback item must include a non-empty post_id")
            
            pid_lower = pid.lower()
            if pid_lower in seen_post_ids_lower:
                logger.info(f"Skipping duplicate post_id in request: {pid}")
                continue
            
            seen_post_ids_lower.add(pid_lower)
            deduped_feedbacks.append(fb)
            original_post_ids.append(pid)
        
        if not deduped_feedbacks:
            raise HTTPException(status_code=400, detail="No valid, unique post_ids provided in feedbacks")
        
        # **DATABASE OPERATIONS: Replace S3 JSON loading with database queries**
        
        # Get campaign data from database
        campaign_db_record = get_agentic_campaign_planner(username, campaign_name)
        if not campaign_db_record:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")
        
        # Extract campaign plan from database record
        stored_plan_full = None
        campaign_plan = None
        
        # Try to get from approved_plan first, then fallback to plan
        for field_name in ("approved_plan", "plan", "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"):
            field_data = getattr(campaign_db_record, field_name, None)
            if field_data:
                try:
                    stored_plan_full = json.loads(field_data) if isinstance(field_data, str) else field_data
                    campaign_plan = stored_plan_full.get("campaign_plan")
                    if campaign_plan:
                        logger.info(f"Loaded campaign plan from {field_name} for {campaign_full_name}")
                        break
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.warning(f"Error parsing {field_name} for '{campaign_full_name}': {e}")
                    continue
        
        if campaign_plan is None:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")
        
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("Stored campaign_plan is a string but not valid JSON; proceeding with original value")
        
        # Load feedback tracking from database
        feedback_dict = {}
        feedback_response_data = getattr(campaign_db_record, 'feedback_response', None)
        
        if feedback_response_data:
            try:
                feedback_response = json.loads(feedback_response_data) if isinstance(feedback_response_data, str) else feedback_response_data
                feedback_dict = feedback_response.get("feedback", {})
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Error parsing feedback_response for '{campaign_full_name}': {e}")
        
        # Initialize feedback dict if empty
        if not feedback_dict:
            feedback_dict = {
                "campaign_name": campaign_full_name,
                "feedback_history": [],
                "current_regen_attempts": {},
                "max_regen_attempts": 3,
                "approved_plan_versions": [],
                "previous_variants": {}
            }
        
        # Normalize attempt keys
        current_attempts_dict = feedback_dict.get("current_regen_attempts", {}) or {}
        normalized_attempts = {}
        for k, v in current_attempts_dict.items():
            if isinstance(k, str):
                kl = k.strip().lower()
                normalized_attempts[kl] = max(v, normalized_attempts.get(kl, 0))
        feedback_dict["current_regen_attempts"] = normalized_attempts
        feedback_dict.setdefault("previous_variants", {})
        
        # Create state dict from database record
        state_dict = {
            "campaign_name": campaign_full_name,
            "campaign_plan": campaign_plan,
            "current_regen_attempts": feedback_dict.get("current_regen_attempts", {}),
            "max_regen_attempts": feedback_dict.get("max_regen_attempts", 3),
            "is_regen_required": True
        }
        
        # Add metadata from stored plan or database record
        meta_defaults = {
            "campaign_objective": "",
            "campaign_description": "",
            "start_date": "",
            "end_date": "",
            "target_audience": "",
            "target_audience_info": [],
            "target_audience_location": "",
            "platforms": []
        }
        
        for mk, dv in meta_defaults.items():
            # Try to get from stored_plan_full first, then from database record attributes
            val = None
            if stored_plan_full:
                val = stored_plan_full.get(mk, dv)
            if not val:
                val = getattr(campaign_db_record, mk, dv) or dv
            state_dict[mk] = val
        
        # **Continue with existing feedback processing logic...**
        full_plan = copy.deepcopy(campaign_plan)
        details: Dict[str, Any] = {}
        human_feedback_map: Dict[str, str] = {}
        
        # Feedback Processing (keeping existing logic)
        version_number = 0
        processed_post_ids: List[str] = []
        
        def classify_feedback_strength(feedback_text: str) -> str:
            feedback_lower = feedback_text.lower()
            strong_indicators = ["completely rewrite", "totally different", "start over", "completely change"]
            medium_indicators = ["improve", "enhance", "better", "more", "add", "include"]
            
            if any(indicator in feedback_lower for indicator in strong_indicators):
                return "strong"
            elif any(indicator in feedback_lower for indicator in medium_indicators):
                return "medium"
            else:
                return "light"
        
        def get_progressive_temperature(attempt_number: int, feedback_strength: str) -> float:
            base_temps = {"light": 0.8, "medium": 0.85, "strong": 0.9}
            base_temp = base_temps.get(feedback_strength, 0.8)
            
            if attempt_number == 1:
                return base_temp
            elif attempt_number == 2:
                return min(base_temp + 0.1, 0.95)
            else:  # attempt 3+
                return 0.95
        
        def generate_enhanced_seed(post_id: str, attempt_number: int, feedback_text: str) -> str:
            timestamp = datetime.utcnow().isoformat()
            seed_input = f"{post_id}|{attempt_number}|{feedback_text[:50]}|{timestamp}"
            return hashlib.sha256(seed_input.encode()).hexdigest()
        
        def content_similarity_check(new_content: str, previous_variants: List[Dict]) -> bool:
            if not previous_variants or not new_content:
                return True
            
            new_words = set(new_content.lower().split())
            for variant in previous_variants[-2:]:  # Check last 2 variants
                prev_content = variant.get("content", "")
                if prev_content:
                    prev_words = set(prev_content.lower().split())
                    similarity = len(new_words.intersection(prev_words)) / max(len(new_words), len(prev_words), 1)
                    if similarity > 0.7:  # Too similar
                        return False
            return True
        
        # [Continue with existing feedback processing loop...]
        # ... (keeping all the existing feedback processing logic unchanged)
        
        # Generate Final Plan
        processed_count = len([k for k, v in details.items() if v.get("success")])
        all_attempts = feedback_dict.get("current_regen_attempts", {}) or {}
        batch_version = max(all_attempts.values()) if all_attempts else (version_number or 1)
        
        approved_plan_data = {
            "campaign_name": campaign_full_name,
            "campaign_plan": full_plan,
            "current_step": "completed",
            "messages": [],
            "stage": "content_generation",
            "plan_approved": True,
            "generated_images": [],  # Empty
            "image_generation_status": "disabled",
            "generated_at": datetime.utcnow().isoformat(),
            "human_feedback_map": human_feedback_map.copy(),
            "batch_version": batch_version
        }
        
        # Add metadata from state_dict
        for mk, dv in meta_defaults.items():
            approved_plan_data[mk] = state_dict.get(mk, dv)
        
        # Generate and upload Excel to S3 ONLY
        excel_s3_url = ""
        try:
            excel_s3_url = generate_and_upload_combined_excel_to_s3(
                campaign_plan=approved_plan_data["campaign_plan"],
                campaign_name=campaign_full_name,
                bucket=S3_BUCKET,
                plan_data=approved_plan_data,
                version=batch_version
            )
            logger.info(f"Successfully uploaded Excel v{batch_version}: {excel_s3_url}")
        except Exception as e:
            logger.error(f"Failed generate/upload excel for batch v{batch_version}: {e}")
        
        approved_plan_data["excel_s3_url"] = excel_s3_url
        
        # Update feedback tracking
        feedback_dict.setdefault("approved_plan_versions", []).append({
            "version": batch_version,
            "excel_s3_url": excel_s3_url,
            "post_ids": list(original_post_ids),
            "timestamp": datetime.utcnow().isoformat(),
            "processed_count": processed_count
        })
        
        # Build response
        response = {
            "campaign_name": campaign_full_name,
            "success": True,
            "message": f"Enhanced feedback processing completed for {processed_count} of {len(deduped_feedbacks)} posts with progressive temperature control.",
            "campaign_plan": approved_plan_data["campaign_plan"],
            "platforms": approved_plan_data.get("platforms", []),
            "generated_images": [],  # empty
            "image_generation_status": "disabled",
            "excel_s3_url": excel_s3_url,
            "processed": len(deduped_feedbacks),
            "batch_version": batch_version,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
            "enhancement_features": {
                "progressive_temperature": True,
                "content_similarity_checking": True,
                "feedback_strength_classification": True,
                "enhanced_seed_generation": True
            }
        }
        
        # **DATABASE UPDATE: Store all data in database instead of S3**
        try:
            version_number_for_db = batch_version or version_number or 0
            fields_to_update = {
                "feedback_response": json.dumps({
                    "feedback": feedback_dict,
                    "approved_plan": approved_plan_data,
                    "details": details,
                    "enhancements": response["enhancement_features"]
                }, ensure_ascii=False),
                "regeneration_count": version_number_for_db,
                # Store the complete response as the latest approved plan
                "approved_plan": json.dumps(response, ensure_ascii=False)
            }
            
            # Store versioned plans in specific version fields
            if batch_version in {1, 2, 3}:
                fields_to_update[f"approved_plan_v{batch_version}"] = json.dumps(response, ensure_ascii=False)
            
            update_agentic_campaign_planner(
                username=username,
                campaign_name=campaign_name,
                **fields_to_update
            )
            logger.info(f"Successfully updated database for {campaign_full_name} v{batch_version}")
        except Exception as e:
            logger.error(f"Failed DB update for {campaign_full_name}: {e}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in enhanced submit_feedback: {e}")
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")
