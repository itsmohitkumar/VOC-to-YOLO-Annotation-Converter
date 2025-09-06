@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Feedback batch regeneration (DB-backed):
    - Reads stored plan / feedback from DB (agentic_campaign_planner) instead of S3 JSON.
    - Produces versioned approved_plan_v{batch_version} and updates DB with feedback_response.
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

        # --- Load plan/approve/feedback records from DB (agentic_campaign_planner) ---
        query = text("""
            SELECT plan_response, approve_response, feedback_response
            FROM agentic_campaign_planner
            WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
              AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
        """)
        row = execute_query(query, params={"username": username, "campaign_name": campaign_name}, fetch_one=True)
        if not row:
            raise HTTPException(status_code=404, detail=f"No planner record found for '{campaign_full_name}'")

        plan_raw = row[0]
        approve_raw = row[1]
        fb_raw = row[2]

        stored_plan_full = None
        campaign_plan = None

        # Prefer approve_response then plan_response (attempt to parse JSON)
        for raw in (approve_raw, plan_raw):
            if not raw:
                continue
            try:
                parsed = raw if isinstance(raw, dict) else json.loads(raw)
                stored_plan_full = parsed
                campaign_plan = parsed.get("campaign_plan") or parsed.get("plan") or parsed.get("campaignPlan") or parsed
                logger.info(f"Loaded plan data from DB for {campaign_full_name}")
                break
            except Exception:
                # fallback to raw string/dict
                try:
                    stored_plan_full = {"campaign_plan": raw}
                    campaign_plan = raw
                    logger.warning("Plan raw exists but could not be parsed as JSON; using raw value")
                    break
                except Exception:
                    continue

        if campaign_plan is None:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")

        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("Stored campaign_plan is a string but not valid JSON; proceeding with original value")

        # --- Load feedback tracking from db feedback_response (if present) or init default ---
        feedback_dict = {}
        if fb_raw:
            try:
                feedback_dict = fb_raw if isinstance(fb_raw, dict) else json.loads(fb_raw)
            except Exception as e:
                logger.warning(f"Could not parse feedback_response JSON from DB for {campaign_full_name}: {e}")
                feedback_dict = {}
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

        # --- Load state (plan.json equivalent) from plan_response or fallback ---
        state_dict = {}
        if plan_raw:
            try:
                state_dict = plan_raw if isinstance(plan_raw, dict) else json.loads(plan_raw)
            except Exception as e:
                logger.warning(f"Could not parse plan_response JSON from DB for {campaign_full_name}: {e}")
                state_dict = {}
        if not state_dict:
            state_dict = {
                "campaign_name": campaign_full_name,
                "campaign_plan": campaign_plan,
                "current_regen_attempts": feedback_dict.get("current_regen_attempts", {}),
                "max_regen_attempts": feedback_dict.get("max_regen_attempts", 3),
                "is_regen_required": True
            }

        full_plan = copy.deepcopy(campaign_plan)
        details: Dict[str, Any] = {}
        human_feedback_map: Dict[str, str] = {}

        # --- helper functions (kept same) ---
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
            else:
                return 0.95

        def generate_enhanced_seed(post_id: str, attempt_number: int, feedback_text: str) -> str:
            timestamp = datetime.utcnow().isoformat()
            seed_input = f"{post_id}|{attempt_number}|{feedback_text[:50]}|{timestamp}"
            return hashlib.sha256(seed_input.encode()).hexdigest()

        def content_similarity_check(new_content: str, previous_variants: List[Dict]) -> bool:
            if not previous_variants or not new_content:
                return True
            new_words = set(new_content.lower().split())
            for variant in previous_variants[-2:]:
                prev_content = variant.get("content", "")
                if prev_content:
                    prev_words = set(prev_content.lower().split())
                    similarity = len(new_words.intersection(prev_words)) / max(len(new_words), len(prev_words), 1)
                    if similarity > 0.7:
                        return False
            return True

        version_number = 0
        processed_post_ids: List[str] = []

        # --- Main feedback loop (unchanged logic, except DB-based read/write) ---
        for fb in deduped_feedbacks:
            post_id = (fb.post_id or "").strip()
            pid_norm = post_id.lower()
            fb_text = (fb.feedback_text or "").strip()

            # Parse post_id
            parts = post_id.split('_')
            if len(parts) >= 3:
                platform_key = parts[0]
                week_key = f"{parts[1]}_{parts[2]}"
                day_key = '_'.join(parts[3:]) if len(parts) > 3 else 'Day_1'
            else:
                platform_key = week_key = day_key = None

            # Validate post exists in full_plan
            try:
                if not (platform_key and
                        platform_key in full_plan and
                        isinstance(full_plan[platform_key], dict) and
                        week_key in full_plan[platform_key] and
                        isinstance(full_plan[platform_key][week_key], dict) and
                        day_key in full_plan[platform_key][week_key]):
                    details[post_id] = {"success": False, "message": f"Post ID '{post_id}' not found in campaign plan."}
                    continue
            except Exception:
                details[post_id] = {"success": False, "message": f"Post ID '{post_id}' not found in campaign plan."}
                continue

            # Attempt limits
            current_regen_attempts = feedback_dict.get("current_regen_attempts", {})
            current_attempts = current_regen_attempts.get(pid_norm, 0)
            max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)
            if current_attempts >= max_regen_attempts:
                feedback_dict.setdefault("feedback_history", []).append({
                    "post_id": post_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "feedback_text": fb_text,
                    "regen_attempt_number": current_attempts + 1,
                    "note": "Max attempts reached"
                })
                details[post_id] = {
                    "success": False,
                    "message": f"Maximum regeneration attempts ({max_regen_attempts}) reached for '{post_id}'",
                    "regeneration_attempts": current_attempts
                }
                continue

            # Record feedback and increment attempts
            feedback_dict.setdefault("feedback_history", []).append({
                "post_id": post_id,
                "timestamp": datetime.utcnow().isoformat(),
                "feedback_text": fb_text,
                "regen_attempt_number": current_attempts + 1,
                "feedback_strength": classify_feedback_strength(fb_text)
            })
            current_regen_attempts[pid_norm] = current_attempts + 1
            feedback_dict["current_regen_attempts"] = current_regen_attempts
            human_feedback_map[post_id] = fb_text
            version_number = current_regen_attempts.get(pid_norm, 1)
            processed_post_ids.append(post_id)

            # Enhanced regeneration input state
            feedback_strength = classify_feedback_strength(fb_text)
            temperature = get_progressive_temperature(version_number, feedback_strength)
            enhanced_seed = generate_enhanced_seed(post_id, version_number, fb_text)

            previous_variants = feedback_dict.get("previous_variants", {}).get(pid_norm, [])
            state_input = {
                **state_dict,
                **feedback_dict,
                "stage": "content_generation",
                "plan_approved": True,
                "base_plan_dict": state_dict.get("base_plan_dict", campaign_plan),
                "current_post_id": post_id,
                "regen_attempt_number": version_number,
                "human_feedback_text": fb_text,
                "feedback_strength": feedback_strength,
                "is_regeneration": True,
                "skip_vector_db": False,
                "variation_index": version_number,
                "random_seed": enhanced_seed,
                "force_variation": True,
                "temperature_override": temperature,
                "previous_variants": previous_variants,
                "similarity_check_required": True,
                "generate_images": False,
                "image_generation_enabled": False
            }

            max_retry_attempts = 3
            successful_regeneration = False
            new_day_node = None
            final_state_dict = {}

            for retry in range(max_retry_attempts):
                try:
                    if retry > 0:
                        state_input["random_seed"] = f"{enhanced_seed}_retry_{retry}"
                        state_input["temperature_override"] = min(temperature + (retry * 0.02), 0.98)

                    final_state = await system_agents.ainvoke(state_input)
                    final_state_dict = dict(final_state)

                    agent_plan = final_state_dict.get("campaign_plan")
                    if isinstance(agent_plan, str):
                        try:
                            agent_plan = json.loads(agent_plan)
                        except json.JSONDecodeError:
                            agent_plan = None

                    if isinstance(agent_plan, dict):
                        try:
                            new_day_node = agent_plan.get(platform_key, {}).get(week_key, {}).get(day_key)
                        except Exception:
                            new_day_node = None

                    if isinstance(new_day_node, dict):
                        new_content = new_day_node.get("content", "")
                        if content_similarity_check(new_content, previous_variants):
                            successful_regeneration = True
                            break
                        elif retry < max_retry_attempts - 1:
                            logger.info(f"Content too similar to previous variants for {post_id}, retrying with higher temperature")
                            continue
                    else:
                        successful_regeneration = True
                        break

                except Exception as e:
                    logger.error(f"Error regenerating {post_id} (retry {retry}): {e}")
                    if retry == max_retry_attempts - 1:
                        details[post_id] = {"success": False, "message": f"Error during regeneration: {str(e)}"}
                        continue

            if not successful_regeneration:
                details[post_id] = {"success": False, "message": f"Failed to generate sufficiently different content after {max_retry_attempts} attempts"}
                continue

            # Process successful regeneration / merge
            if isinstance(new_day_node, dict):
                merged_node = copy.deepcopy(new_day_node)
            else:
                existing = full_plan[platform_key][week_key].get(day_key, {})
                merged_node = {}
                if isinstance(existing, dict):
                    merged_node.update(existing)
                fallback_keys = (
                    "task", "content", "caption", "headline", "cta",
                    "hook", "angle", "hashtags", "title", "body", "notes"
                )
                for k in fallback_keys:
                    if k in final_state_dict:
                        merged_node[k] = final_state_dict[k]

            # Clean up any image-related fields (kept)
            image_related_keys = ["image_path_s3", "image_paths", "image_urls", "images", "image_prompt"]
            for img_key in image_related_keys:
                if img_key in merged_node:
                    merged_node[img_key] = []
            merged_node["human_feedback"] = fb_text
            merged_node["regeneration_count"] = version_number
            merged_node["feedback_strength"] = feedback_strength
            merged_node["temperature_used"] = temperature
            full_plan[platform_key][week_key][day_key] = merged_node

            # Store variant for future similarity checking
            pv_map = feedback_dict.setdefault("previous_variants", {})
            pv_list = pv_map.get(pid_norm, [])
            variant_snapshot = {
                k: merged_node.get(k)
                for k in ("content", "caption", "headline", "cta", "hook", "angle", "hashtags", "title", "body", "notes")
                if k in merged_node
            }
            variant_snapshot["timestamp"] = datetime.utcnow().isoformat()
            variant_snapshot["temperature"] = temperature
            variant_snapshot["attempt"] = version_number
            pv_list.append(variant_snapshot)
            pv_map[pid_norm] = pv_list
            feedback_dict["previous_variants"] = pv_map

            details[post_id] = {
                "success": True,
                "message": "Feedback processed and post regenerated with enhanced variation",
                "regeneration_attempts": version_number,
                "feedback_strength": feedback_strength,
                "temperature_used": temperature
            }

        # --- Generate Final Plan object ---
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

        # Add metadata from state_dict then stored_plan_full then defaults
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
            val = state_dict.get(mk) if state_dict.get(mk) is not None else (stored_plan_full.get(mk) if stored_plan_full and isinstance(stored_plan_full, dict) else dv)
            approved_plan_data[mk] = val

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

        # Update feedback tracking in database (append to approved_plan_versions)
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

        # Update database with enhanced feedback response
        try:
            version_number_for_db = batch_version or version_number or 0
            fields_to_update = {
                "feedback_response": json.dumps({
                    "feedback": feedback_dict,
                    "approved_plan": approved_plan_data,
                    "details": details,
                    "enhancements": response["enhancement_features"]
                }, ensure_ascii=False),
                "regeneration_count": version_number_for_db
            }
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
