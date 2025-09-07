# src/agent/graph.py

from typing import Dict, Any
from langgraph.graph import StateGraph
from src.models import State

from src.campaign_agent.system_agents import (
    orchestrator_agent,
    system_agent_orchestrator,
    prompt_optimization,
    text_generator,
    content_reviewer,
    plan_generator,
    content_validator,
    web_search_tool,
    PLATFORM_AGENT_MAP
)

from src.agent.campaign_agent.social_media_agents import (
    social_media_agents_supervisor,
    create_instagram_post,
    create_facebook_post,
    create_x_post,
    create_whatsapp_post,
    create_email_post,
    create_sms_post
)

# ------------------------ BUILD GRAPH ------------------------
graph = StateGraph(State)

# ------------------------ SYSTEM AGENT NODES ------------------------
graph.add_node("orchestrator_agent", orchestrator_agent)
graph.add_node("system_agent_orchestrator", system_agent_orchestrator)

def web_search_agent(state: State) -> Dict[str, Any]:
    """Web search agent that uses the web search tool."""
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")

    search_query = f"{campaign_objective} {campaign_description} {target_audience} marketing campaign trends 2024"

    try:
        search_results = web_search_tool.invoke(search_query)
        return {
            "messages": [f"Web search completed for: {search_query[:100]}..."],
            "current_step": "web_search_agent",
            "search_results": search_results,
            "search_query": search_query
        }
    except Exception as e:
        return {
            "messages": [f"Web search failed: {str(e)}"],
            "current_step": "web_search_agent",
            "search_results": "No web search results available",
            "search_query": search_query
        }

graph.add_node("web_search_agent", web_search_agent)
graph.add_node("prompt_optimization", prompt_optimization)
graph.add_node("text_generator", text_generator)
graph.add_node("content_reviewer", content_reviewer)
graph.add_node("plan_generator", plan_generator)
graph.add_node("content_validator", content_validator)

# ------------------------ SOCIAL MEDIA AGENT NODES ------------------------
graph.add_node("social_media_agents_supervisor", social_media_agents_supervisor)
graph.add_node("create_instagram_post", create_instagram_post)
graph.add_node("create_facebook_post", create_facebook_post)
graph.add_node("create_x_post", create_x_post)
graph.add_node("create_whatsapp_post", create_whatsapp_post)
graph.add_node("create_email_post", create_email_post)
graph.add_node("create_sms_post", create_sms_post)

# ------------------------ ENTRY POINT ------------------------
graph.set_entry_point("orchestrator_agent")

# ------------------------ REGENERATION ROUTER (FIXED) ------------------------
def regeneration_router(state: State) -> str:
    if state.get("is_regeneration", False):
        # In regeneration mode, route directly to the specific platform agent
        current_post_id = state.get("current_post_id")
        if current_post_id:
            platform = current_post_id.split('_')[0].lower()
            if platform in PLATFORM_AGENT_MAP:
                print(f"🔄 Regeneration mode: Routing directly to {platform} agent for post_id: {current_post_id}")
                return f"create_{platform}_post"
            else:
                print(f"⚠️ Unknown platform in post_id: {current_post_id}")
                return "__end__"
        else:
            print("⚠️ Regeneration mode but no current_post_id specified")
            return "__end__"
    else:
        print("🔄 Normal mode: Proceeding to stage router")
        return stage_router(state)

graph.add_conditional_edges(
    "orchestrator_agent",
    regeneration_router,
    {
        "create_instagram_post": "create_instagram_post",
        "create_facebook_post": "create_facebook_post", 
        "create_x_post": "create_x_post",
        "create_whatsapp_post": "create_whatsapp_post",
        "create_email_post": "create_email_post",
        "create_sms_post": "create_sms_post",
        "plan_generator": "plan_generator",
        "system_agent_orchestrator": "system_agent_orchestrator"
    }
)

# ------------------------ STAGE ROUTING ------------------------
def stage_router(state: State) -> str:
    current_stage = state.get("stage", "plan_generation")
    plan_approved = state.get("plan_approved", False)
    print(f"🔄 Stage Router: current_stage={current_stage}, plan_approved={plan_approved}")
    if current_stage == "plan_generation":
        print("📋 Routing to plan_generator for plan generation stage")
        return "plan_generator"
    elif current_stage == "content_generation" and plan_approved:
        print("📝 Routing to system_agent_orchestrator for content generation stage")
        return "system_agent_orchestrator"
    else:
        print("📋 Default routing to plan_generator")
        return "plan_generator"

# ------------------------ STAGE 1: PLAN GENERATION ------------------------
graph.add_edge("plan_generator", "__end__")

# ------------------------ STAGE 2: CONTENT GENERATION WORKFLOW ------------------------
graph.add_edge("system_agent_orchestrator", "web_search_agent")
graph.add_edge("web_search_agent", "prompt_optimization")
graph.add_edge("prompt_optimization", "text_generator")
graph.add_edge("text_generator", "content_reviewer")
graph.add_edge("content_reviewer", "content_validator")

# ------------------------ PHASE 3: SOCIAL MEDIA AGENTS WORKFLOW ------------------------
graph.add_edge("content_validator", "social_media_agents_supervisor")

def social_media_router(state: State) -> str:
    current_post_id = state.get("current_post_id")
    if current_post_id:
        platform = current_post_id.split('_')[0].lower()
        if platform in PLATFORM_AGENT_MAP:
            print(f"🔄 Routing to {platform} agent for post_id: {current_post_id}")
            return f"create_{platform}_post"
        else:
            print(f"⚠️ Unknown platform in post_id: {current_post_id}")
            return "__end__"
    else:
        platforms = state.get("platforms", ["instagram"])
        if "instagram" in platforms:
            return "create_instagram_post"
        elif "facebook" in platforms:
            return "create_facebook_post"
        elif "x" in platforms:
            return "create_x_post"
        elif "whatsapp" in platforms:
            return "create_whatsapp_post"
        elif "email" in platforms:
            return "create_email_post"
        elif "sms" in platforms:
            return "create_sms_post"
        else:
            return "create_instagram_post"

graph.add_conditional_edges(
    "social_media_agents_supervisor",
    social_media_router,
    ["create_instagram_post", "create_facebook_post", "create_x_post",
     "create_whatsapp_post", "create_email_post", "create_sms_post"]
)

# All platform agents end after execution (both normal and regeneration mode)
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()



# Fixed feedback API implementation

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    FIXED: Feedback batch regeneration with proper content extraction and merging.
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing enhanced multi-feedback for {campaign_full_name}")
        
        # Validations (unchanged)
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
        
        # Deduplicate feedbacks (unchanged)
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
        
        # Load plans and stored state from DB (unchanged)
        stored_plan_full = None
        campaign_plan = None
        planner_record = get_agentic_planner_record(username=username, campaign_name=campaign_name)
        if not planner_record:
            raise HTTPException(status_code=404, detail=f"No planner record found for '{campaign_full_name}'")
        
        # Load plan from DB (unchanged logic)
        for candidate_key in ("approve_response", "plan_response"):
            raw = planner_record.get(candidate_key)
            if not raw:
                continue
            try:
                parsed = raw if isinstance(raw, dict) else json.loads(raw)
                stored_plan_full = parsed
                campaign_plan = parsed.get("campaign_plan") or parsed.get("plan") or parsed.get("campaignPlan") or parsed
                logger.info(f"Loaded {candidate_key} from DB for {campaign_full_name}")
                break
            except Exception:
                try:
                    stored_plan_full = {"campaign_plan": raw}
                    campaign_plan = raw
                    logger.warning(f"{candidate_key} exists but could not be parsed as JSON; using raw value")
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
        
        # Load feedback tracking from DB (unchanged)
        feedback_dict = {}
        fb_raw = planner_record.get("feedback_response")
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
        
        # Normalize attempt keys (unchanged)
        current_attempts_dict = feedback_dict.get("current_regen_attempts", {}) or {}
        normalized_attempts = {}
        for k, v in current_attempts_dict.items():
            if isinstance(k, str):
                kl = k.strip().lower()
                normalized_attempts[kl] = max(v, normalized_attempts.get(kl, 0))
        feedback_dict["current_regen_attempts"] = normalized_attempts
        feedback_dict.setdefault("previous_variants", {})
        
        # Load state from DB (unchanged)
        state_dict = {}
        plan_raw = planner_record.get("plan_response")
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
        
        # Pre-check for max attempts (unchanged)
        current_regen_attempts = feedback_dict.get("current_regen_attempts", {})
        max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)
        for fb in deduped_feedbacks:
            pid_norm = fb.post_id.lower()
            current_attempts = current_regen_attempts.get(pid_norm, 0)
            if current_attempts >= max_regen_attempts:
                raise HTTPException(status_code=400, detail=f"Max regeneration attempts reached for post_id '{fb.post_id}'")
        
        # Helper functions (unchanged)
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
        
        # MAIN FEEDBACK LOOP - FIXED VERSION
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
            
            # Check attempt limits
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
            
            # Enhanced regeneration parameters
            feedback_strength = classify_feedback_strength(fb_text)
            temperature = get_progressive_temperature(version_number, feedback_strength)
            enhanced_seed = generate_enhanced_seed(post_id, version_number, fb_text)
            
            previous_variants = feedback_dict.get("previous_variants", {}).get(pid_norm, [])
            
            # FIXED: Simplified state input for direct platform agent invocation
            state_input = {
                **state_dict,
                "stage": "content_generation",
                "plan_approved": True,
                "campaign_plan": full_plan,  # Pass the full plan
                "current_post_id": post_id,
                "regen_attempt_number": version_number,
                "human_feedback_text": fb_text,
                "feedback_strength": feedback_strength,
                "is_regeneration": True,  # This is key - triggers direct routing
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
            new_content = ""
            final_state_dict = {}
            
            for retry in range(max_retry_attempts):
                try:
                    if retry > 0:
                        state_input["random_seed"] = f"{enhanced_seed}_retry_{retry}"
                        state_input["temperature_override"] = min(temperature + (retry * 0.02), 0.98)
                    
                    # FIXED: Call agent system with proper regeneration state
                    final_state = await system_agents.ainvoke(state_input)
                    final_state_dict = dict(final_state)
                    
                    # FIXED: Extract content directly from the agent response
                    # The platform agent returns content in the state directly
                    new_content = final_state_dict.get("content", "")
                    
                    # Alternative extraction methods if content not found directly
                    if not new_content:
                        # Try to get content from platform-specific key
                        platform_post_key = f"{platform_key}_post"
                        platform_post = final_state_dict.get(platform_post_key, {})
                        if isinstance(platform_post, dict):
                            new_content = platform_post.get("content", "")
                    
                    # If still no content, try from campaign_plan structure
                    if not new_content:
                        agent_plan = final_state_dict.get("campaign_plan")
                        if isinstance(agent_plan, dict):
                            try:
                                new_day_node = agent_plan.get(platform_key, {}).get(week_key, {}).get(day_key)
                                if isinstance(new_day_node, dict):
                                    new_content = new_day_node.get("content", "")
                            except Exception:
                                pass
                    
                    # Check if we got new content
                    if new_content and new_content.strip():
                        # Check similarity with previous variants
                        if content_similarity_check(new_content, previous_variants):
                            successful_regeneration = True
                            logger.info(f"Successfully regenerated content for {post_id} (retry {retry})")
                            break
                        elif retry < max_retry_attempts - 1:
                            logger.info(f"Content too similar to previous variants for {post_id}, retrying with higher temperature")
                            continue
                    else:
                        logger.warning(f"No content generated for {post_id} (retry {retry})")
                        if retry < max_retry_attempts - 1:
                            continue
                    
                except Exception as e:
                    logger.error(f"Error regenerating {post_id} (retry {retry}): {e}")
                    if retry == max_retry_attempts - 1:
                        details[post_id] = {"success": False, "message": f"Error during regeneration: {str(e)}"}
                        continue
            
            if not successful_regeneration or not new_content:
                details[post_id] = {"success": False, "message": f"Failed to generate new content after {max_retry_attempts} attempts"}
                continue
            
            # FIXED: Merge the regenerated content properly
            existing_node = full_plan[platform_key][week_key].get(day_key, {})
            if isinstance(existing_node, dict):
                merged_node = copy.deepcopy(existing_node)
            else:
                merged_node = {}
            
            # Update with new content
            merged_node["content"] = new_content
            
            # Get other fields from the agent response if available
            task_description = final_state_dict.get("task_description")
            if task_description:
                merged_node["task"] = task_description
            
            # Add regeneration metadata
            merged_node["human_feedback"] = fb_text
            merged_node["regenration_count"] = version_number  # Note: keeping original typo for consistency
            merged_node["feedback_strength"] = feedback_strength
            merged_node["temperature_used"] = temperature
            
            # Clean up image-related fields
            image_related_keys = ["image_path_s3", "image_paths", "image_urls", "images", "image_prompt"]
            for img_key in image_related_keys:
                if img_key in merged_node:
                    merged_node[img_key] = []
            
            # Update the full plan
            full_plan[platform_key][week_key][day_key] = merged_node
            
            # Store variant for future similarity checking
            pv_map = feedback_dict.setdefault("previous_variants", {})
            pv_list = pv_map.get(pid_norm, [])
            variant_snapshot = {
                "content": new_content,
                "timestamp": datetime.utcnow().isoformat(),
                "temperature": temperature,
                "attempt": version_number
            }
            # Add other relevant fields
            for k in ("caption", "headline", "cta", "hook", "angle", "hashtags", "title", "body", "notes"):
                if k in merged_node:
                    variant_snapshot[k] = merged_node.get(k)
            
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
            
            logger.info(f"Successfully processed feedback for {post_id}: New content length = {len(new_content)}")
        
        # Generate final response (rest of the code unchanged)
        processed_count = len([k for k, v in details.items() if v.get("success")])
        all_attempts = feedback_dict.get("current_regen_attempts", {}) or {}
        
        # Incremental batch_version based on existing DB versions
        status = get_campaign_status(username, campaign_name)
        existing_versions = sum([
            status["has_approved_plan_v1"],
            status["has_approved_plan_v2"],
            status["has_approved_plan_v3"]
        ])
        batch_version = existing_versions + 1
        
        if batch_version > 3:
            raise HTTPException(status_code=400, detail="Maximum feedback versions (3) reached for this campaign")
        
        approved_plan_data = {
            "campaign_name": campaign_full_name,
            "campaign_plan": full_plan,
            "current_step": "completed",
            "messages": [],
            "stage": "content_generation",
            "plan_approved": True,
            "generated_images": [],
            "image_generation_status": "disabled",
            "generated_at": datetime.utcnow().isoformat(),
            "human_feedback_map": human_feedback_map.copy(),
            "batch_version": batch_version
        }
        
        # Add metadata from stored plan
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
        
        # Generate and upload Excel to S3
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
        
        # Update feedback tracking in database
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
            "generated_images": [],
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
        
        # Update database
        try:
            total_regenerations = sum(all_attempts.values())
            fields_to_update = {
                "feedback_response": json.dumps({
                    "feedback": feedback_dict,
                    "approved_plan": approved_plan_data,
                    "details": details,
                    "enhancements": response["enhancement_features"]
                }, ensure_ascii=False),
                "regenration_count": total_regenerations
            }
            
            if batch_version in {1, 2, 3}:
                fields_to_update[f"approved_plan_v{batch_version}"] = json.dumps(response, ensure_ascii=False)
            
            affected = update_agentic_campaign_planner(
                username=username,
                campaign_name=campaign_name,
                **fields_to_update
            )
            if affected == 0:
                raise ValueError("Database update failed - no rows affected")
            logger.info(f"Successfully updated database for {campaign_full_name} v{batch_version}")
        except Exception as e:
            logger.error(f"Failed DB update for {campaign_full_name}: {e}")
            raise HTTPException(status_code=500, detail="Failed to persist feedback state")
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in enhanced submit_feedback: {e}")
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")



# src/agent/campaign_agent/social_media_agents.py

from typing import Dict, Any
from src.models import State
from src.llm.prompts import (
    INSTAGRAM_CONTENT_GENERATION_PROMPT,
    FACEBOOK_CONTENT_GENERATION_PROMPT,
    X_CONTENT_GENERATION_PROMPT,
    WHATSAPP_CONTENT_GENERATION_PROMPT,
    EMAIL_CONTENT_GENERATION_PROMPT,
    SMS_CONTENT_GENERATION_PROMPT,
    TASK_DESCRIPTION_GENERATION_PROMPT
)
from src.llm.bedrock import call_bedrock_for_text
import time
import random

CONTENT_PROMPT_TEMPLATES = {
    "instagram": INSTAGRAM_CONTENT_GENERATION_PROMPT,
    "facebook": FACEBOOK_CONTENT_GENERATION_PROMPT,
    "x": X_CONTENT_GENERATION_PROMPT,
    "whatsapp": WHATSAPP_CONTENT_GENERATION_PROMPT,
    "email": EMAIL_CONTENT_GENERATION_PROMPT,
    "sms": SMS_CONTENT_GENERATION_PROMPT,
}

def debug_regeneration_state(state: State, platform: str) -> None:
    """Debug function to trace regeneration state."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
    feedback = state.get("human_feedback_text", "")
    attempt = state.get("regen_attempt_number", 0)
    
    print(f"🔍 DEBUG {platform} agent:")
    print(f"   is_regeneration: {is_regen}")
    print(f"   current_post_id: {post_id}")
    print(f"   regen_attempt_number: {attempt}")
    print(f"   has_feedback: {bool(feedback)}")
    print(f"   feedback_preview: {feedback[:50]}..." if feedback else "   feedback_preview: None")

def get_dynamic_temperature(state: State) -> float:
    """Calculate temperature based on feedback strength and regeneration count."""
    strength = state.get("feedback_strength", "medium")
    attempt = state.get("regen_attempt_number", 1)
    base_temps = {"light": 0.75, "medium": 0.80, "strong": 0.85}
    base_temp = base_temps.get(strength, 0.80)
    
    if attempt == 1:
        return base_temp
    elif attempt == 2:
        return min(base_temp + 0.15, 0.95)
    else:  # 3rd+ attempt
        return min(base_temp + 0.25, 1.0)  # Boosted for max variation

def enhance_prompt(prompt: str, state: State) -> str:
    """Add stronger directives for regeneration with variation enforcement."""
    attempt = state.get("regen_attempt_number", 1)
    lines = [
        f"--- REGENERATION ATTEMPT {attempt} (MUST BE DISTINCTLY DIFFERENT) ---"
    ]
    
    strength = state.get("feedback_strength", "medium")
    if strength == "strong":
        lines.append("CRITICAL: Completely rewrite with new structure, wording, and approach. Do NOT reuse any phrases from prior versions.")
    elif strength == "medium":
        lines.append("IMPORTANT: Substantially change content, using alternative angles and messaging while addressing feedback.")
    else:
        lines.append("IMPORTANT: Improve meaningfully with fresh ideas, avoiding repetition of previous content.")
    
    if state.get("previous_variants"):
        prev_count = len(state['previous_variants'])
        lines.append(f"AVOID ANY SIMILARITY to the last {prev_count} versions. Generate entirely new content.")
    
    if state.get("force_variation", False):
        lines.append("VARIATION ENFORCED: This output MUST differ significantly in style, tone, and structure.")
    
    # Add entropy: unique timestamp and random cue
    entropy = f"Generation entropy seed: {time.time()} | Random cue: {random.choice(['creative twist', 'innovative angle', 'fresh perspective', 'bold variation'])}"
    lines.append(entropy)
    
    return prompt + "\n\n" + "\n".join(lines)

def generate_task_description(state: State, phase: str, day_context: str) -> str:
    """Generate task description with slight temperature adjustment."""
    prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=state.get("campaign_objective", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        day_context=day_context
    )
    
    temp = get_dynamic_temperature(state) * 0.90
    try:
        desc = call_bedrock_for_text(prompt, max_tokens=50, temperature=temp).strip()
        if not desc:
            desc = call_bedrock_for_text(prompt, max_tokens=40, temperature=temp + 0.10).strip()
        return desc if len(desc) <= 80 else desc[:77] + "..."
    except Exception:
        return f"Generate strategic content for {state.get('campaign_objective', '').lower()}"

def check_content_variation(new_content: str, previous_variants: list) -> bool:
    """Simple check if new content differs enough from previous (word overlap < 70%)."""
    if not previous_variants:
        return True
    new_words = set(new_content.lower().split())
    for variant in previous_variants:
        prev_words = set(variant.get("content", "").lower().split())
        overlap = len(new_words.intersection(prev_words)) / max(len(new_words), len(prev_words), 1)
        if overlap > 0.7:
            return False
    return True

def create_social_media_post(state: State, platform: str) -> Dict[str, Any]:
    """Generic social media post creator with enhanced regeneration support and debugging."""
    
    # Add debugging for regeneration
    debug_regeneration_state(state, platform)
    
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    
    # Determine campaign phase
    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"
    
    day_context_map = {
        1: "This is the opening/first content piece",
        2: "This is the follow-up content piece",
        3: "This builds momentum from previous content"
    }
    day_context = day_context_map.get(current_day, f"This continues the {phase} phase narrative")
    
    # Generate task description
    task_description = generate_task_description(state, phase, day_context)
    
    # Build base content prompt
    base_content_prompt = CONTENT_PROMPT_TEMPLATES.get(platform, "").format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=state.get("campaign_objective", ""),
        campaign_theme=state.get("campaign_theme", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        web_search_results=state.get("search_results", "")[:500] if state.get("search_results") else "No web search context available",
        context_keywords=', '.join(state.get("optimized_prompts", {}).get("context_keywords", [])),
        context_guidance=state.get("optimized_prompts", {}).get("context_guidance", "")
    )
    
    # Add human feedback if present (this is key for regeneration)
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)
    
    if human_feedback:
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\n"
        base_content_prompt += "IMPORTANT: Incorporate this feedback to improve the post and ensure the new version is distinctly different from the previous version."
    
    # Apply enhanced variation for regenerations
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)
        print(f"🔄 Enhanced prompt for regeneration attempt {regen_attempt}")
    
    # Get dynamic temperature
    temperature = get_dynamic_temperature(state)
    print(f"🌡️ Using temperature: {temperature} for attempt {regen_attempt}")
    
    # Platform-specific max tokens
    max_tokens_map = {
        "instagram": 1000,
        "facebook": 1000,
        "x": 500,
        "whatsapp": 800,
        "email": 1200,
        "sms": 300
    }
    max_tokens = max_tokens_map.get(platform, 1000)
    
    # Generate content with variation check
    previous_variants = state.get("previous_variants", [])
    content = ""
    
    for retry in range(3):  # Retry up to 3 times if too similar
        try:
            print(f"🎯 Generating content for {platform} (retry {retry})")
            content = call_bedrock_for_text(
                prompt=base_content_prompt,
                max_tokens=max_tokens,
                temperature=temperature + (retry * 0.05)  # Slight boost per retry
            )
            
            if content and content.strip():
                if check_content_variation(content, previous_variants):
                    print(f"✅ Content variation check passed for {platform}")
                    break
                else:
                    print(f"⚠️ Content too similar, retrying {platform} generation")
            else:
                print(f"⚠️ Empty content generated for {platform}, retrying")
                
        except Exception as e:
            print(f"❌ Error generating {platform} content (retry {retry}): {str(e)}")
            content = f"Error generating {platform} content: {str(e)}"
            break
    else:
        content += " [NOTE: Variation retry limit reached; content may be similar]"
        print(f"⚠️ Retry limit reached for {platform}")
    
    # Build post response
    post_key = f"{platform}_post"
    post = {
        "task_description": task_description,
        "content": content,
        "regeneration_metadata": {
            "attempt": regen_attempt,
            "temperature_used": temperature,
            "feedback_incorporated": bool(human_feedback),
            "feedback_strength": state.get("feedback_strength", "medium"),
            "seed": state.get("random_seed", ""),
            "generation_timestamp": time.time()
        }
    }
    
    print(f"📄 Generated {platform} content (length: {len(content)})")
    if regen_attempt > 1:
        print(f"🔄 Regeneration complete for {platform}: attempt {regen_attempt}")
    
    return {
        post_key: post,
        "messages": [f"Enhanced {platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f} using AWS Bedrock"],
        "current_step": f"create_{platform}_post",
        "content": content,  # IMPORTANT: Direct content access for extraction
        "task_description": task_description  # IMPORTANT: Direct task access
    }

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """Supervisor agent that coordinates social media content generation."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
    
    print(f"🎭 Social Media Supervisor Debug:")
    print(f"   is_regeneration: {is_regen}")
    print(f"   current_post_id: {post_id}")
    
    return {
        "messages": ["Social media agents supervisor initialized"],
        "current_step": "social_media_agents_supervisor"
    }

# Platform-specific functions using the DRY generic function
def create_instagram_post(state: State) -> Dict[str, Any]:
    """Agent that creates professional Instagram posts using AWS Bedrock."""
    return create_social_media_post(state, "instagram")

def create_facebook_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic Facebook posts using AWS Bedrock."""
    return create_social_media_post(state, "facebook")

def create_x_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic X (Twitter) posts using AWS Bedrock."""
    return create_social_media_post(state, "x")

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic WhatsApp messages using AWS Bedrock."""
    return create_social_media_post(state, "whatsapp")

def create_email_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic email communications using AWS Bedrock."""
    return create_social_media_post(state, "email")

def create_sms_post(state: State) -> Dict[str, Any]:
    """Agent that creates SMS posts using AWS Bedrock."""
    return create_social_media_post(state, "sms")
