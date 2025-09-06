# COMPLETE FIXED src/agent/graph.py

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
# NOTE: image_generator node completely removed
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

# ------------------------ ENHANCED REGENERATION ROUTER ------------------------
def regeneration_router(state: State) -> str:
    """
    FIXED Enhanced regeneration router with comprehensive debugging and validation.
    """
    is_regen = state.get("is_regeneration", False)
    current_post_id = state.get("current_post_id", "")
    stage = state.get("stage", "")
    plan_approved = state.get("plan_approved", False)
    
    # Add comprehensive debugging
    print(f"🔄 Router Debug: is_regeneration={is_regen}, current_post_id='{current_post_id}'")
    print(f"🔄 Router Debug: stage={stage}, plan_approved={plan_approved}")
    
    if is_regen and current_post_id:
        print(f"🔄 Regeneration mode detected: Routing directly to social media supervisor for {current_post_id}")
        return "social_media_agents_supervisor"
    else:
        print("🔄 Normal mode: Proceeding to stage router")
        return stage_router(state)

graph.add_conditional_edges(
    "orchestrator_agent",
    regeneration_router,
    {
        "social_media_agents_supervisor": "social_media_agents_supervisor",
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
# NOTE: Removed image_generator from flow - goes directly to content_reviewer
graph.add_edge("text_generator", "content_reviewer")
graph.add_edge("content_reviewer", "content_validator")

# ------------------------ PHASE 3: SOCIAL MEDIA AGENTS WORKFLOW ------------------------
graph.add_edge("content_validator", "social_media_agents_supervisor")

def social_media_router(state: State) -> str:
    """
    FIXED Enhanced social media router with better debugging and post-specific routing.
    """
    current_post_id = state.get("current_post_id")
    
    print(f"🔄 Social Media Router: current_post_id='{current_post_id}'")
    
    if current_post_id:
        platform = current_post_id.split('_')[0].lower()
        if platform in PLATFORM_AGENT_MAP:
            agent_name = f"create_{platform}_post"
            print(f"🔄 Routing to {agent_name} for specific post: {current_post_id}")
            return agent_name
        else:
            print(f"⚠️ Unknown platform '{platform}' in post_id: {current_post_id}")
            return "__end__"
    else:
        # Default routing when no specific post is targeted
        platforms = state.get("platforms", ["instagram"])
        print(f"🔄 No specific post_id, using default platforms: {platforms}")
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

# In regeneration mode, end after platform agent
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()



# COMPLETE FIXED FEEDBACK API SECTION for src/api/api.py
# Add this import at the top of your api.py if not already present:

from .db_utils import (get_user_by_username, get_user_campaigns, get_campaign_by_name,
                       get_collection_info, hybrid_search, insert_agentic_campaign_planner,
                       update_agentic_campaign_planner, get_agentic_planner_record)  # <- ADD THIS

# Replace the entire submit_feedback function with this FIXED version:

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    FIXED Feedback batch regeneration (DB-backed):
    - Properly constructs state to preserve is_regeneration=True
    - Only regenerates the specific post_id provided in feedback  
    - Enhanced content extraction with dual methods
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

        # --- Load plans and stored state from DB instead of S3 ---
        stored_plan_full = None
        campaign_plan = None
        planner_record = get_agentic_planner_record(username=username, campaign_name=campaign_name)
        if not planner_record:
            raise HTTPException(status_code=404, detail=f"No planner record found for '{campaign_full_name}'")

        # prefer approve_response (approved_plan.json) then plan_response (plan.json)
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
                # if raw is not valid JSON but is a string, still try to keep it as-is
                try:
                    # final attempt: if raw looks like a str but not JSON, wrap into dict
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

        # --- Load feedback tracking from DB (feedback_response) or init default ---
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

        # Normalize attempt keys
        current_attempts_dict = feedback_dict.get("current_regen_attempts", {}) or {}
        normalized_attempts = {}
        for k, v in current_attempts_dict.items():
            if isinstance(k, str):
                kl = k.strip().lower()
                normalized_attempts[kl] = max(v, normalized_attempts.get(kl, 0))
        feedback_dict["current_regen_attempts"] = normalized_attempts
        feedback_dict.setdefault("previous_variants", {})

        # --- Load state (plan.json equivalent) from DB plan_response or fallback ---
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

        # --- Main feedback loop (FIXED STATE CONSTRUCTION) ---
        for fb in deduped_feedbacks:
            post_id = (fb.post_id or "").strip()
            pid_norm = post_id.lower()
            fb_text = (fb.feedback_text or "").strip()

            logger.info(f"Processing feedback for post_id: {post_id} with text: '{fb_text}'")

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

            # CRITICAL FIX: Properly construct state to ensure is_regeneration=True
            logger.info(f"🔧 Constructing state for regeneration of {post_id}")
            
            # Build base regeneration state FIRST (with regeneration flags)
            base_regeneration_state = {
                "stage": "content_generation",
                "plan_approved": True,
                "is_regeneration": True,           # ← Set this FIRST
                "current_post_id": post_id,
                "regen_attempt_number": version_number,
                "human_feedback_text": fb_text,
                "feedback_strength": feedback_strength,
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

            # Now merge with other state, but preserve regeneration settings
            state_input = {}
            state_input.update(state_dict)              # Add stored state
            state_input.update(feedback_dict)           # Add feedback tracking  
            state_input.update(base_regeneration_state) # Override with regeneration settings
            state_input["base_plan_dict"] = state_dict.get("base_plan_dict", campaign_plan)

            # DOUBLE-CHECK: Ensure critical flags are preserved
            state_input["is_regeneration"] = True
            state_input["current_post_id"] = post_id

            logger.info(f"🔧 State constructed: is_regeneration={state_input.get('is_regeneration')}, current_post_id='{state_input.get('current_post_id')}'")

            max_retry_attempts = 3
            successful_regeneration = False
            new_day_node = None
            final_state_dict = {}

            for retry in range(max_retry_attempts):
                try:
                    if retry > 0:
                        state_input["random_seed"] = f"{enhanced_seed}_retry_{retry}"
                        state_input["temperature_override"] = min(temperature + (retry * 0.02), 0.98)

                    logger.info(f"🔧 Invoking system_agents for {post_id} (attempt {retry + 1})")
                    final_state = await system_agents.ainvoke(state_input)
                    final_state_dict = dict(final_state)
                    logger.info(f"🔧 Agent response received for {post_id}")

                    # ENHANCED CONTENT EXTRACTION - Try both methods
                    new_content = ""
                    new_task = ""
                    
                    # Method 1: Try campaign_plan structure
                    agent_plan = final_state_dict.get("campaign_plan")
                    if isinstance(agent_plan, str):
                        try:
                            agent_plan = json.loads(agent_plan)
                        except json.JSONDecodeError:
                            agent_plan = None

                    new_day_node = None
                    if isinstance(agent_plan, dict):
                        try:
                            new_day_node = agent_plan.get(platform_key, {}).get(week_key, {}).get(day_key)
                            if isinstance(new_day_node, dict):
                                new_content = new_day_node.get("content", "")
                                new_task = new_day_node.get("task", "")
                                logger.info(f"🔧 Extracted content via campaign_plan structure for {post_id}")
                        except Exception as e:
                            logger.warning(f"Failed to extract via campaign_plan structure: {e}")
                            new_day_node = None

                    # Method 2: Try direct extraction from final_state_dict
                    if not new_day_node or not new_content:
                        new_content = final_state_dict.get("content", "")
                        new_task = final_state_dict.get("task_description", "")
                        
                        if new_content:
                            new_day_node = {
                                "task": new_task or f"Regenerated {platform_key} content",
                                "content": new_content,
                                "human_feedback": fb_text,
                                "regeneration_count": version_number,
                                "feedback_strength": feedback_strength,
                                "temperature_used": temperature
                            }
                            logger.info(f"🔧 Extracted content via direct method for {post_id}")

                    # Check if we got valid content
                    if new_day_node and isinstance(new_day_node, dict) and new_day_node.get("content"):
                        content_to_check = new_day_node.get("content", "")
                        if content_similarity_check(content_to_check, previous_variants):
                            successful_regeneration = True
                            logger.info(f"✅ Successful regeneration for {post_id} with new content")
                            break
                        elif retry < max_retry_attempts - 1:
                            logger.info(f"Content too similar to previous variants for {post_id}, retrying with higher temperature")
                            continue
                    
                    # If we didn't get a proper day node but have some content, use it
                    if new_content and not new_day_node:
                        new_day_node = {
                            "task": new_task or f"Regenerated {platform_key} content for {day_key}",
                            "content": new_content,
                            "human_feedback": fb_text,
                            "regeneration_count": version_number,
                            "feedback_strength": feedback_strength,
                            "temperature_used": temperature
                        }
                        successful_regeneration = True
                        logger.info(f"✅ Using extracted content for {post_id}")
                        break
                    
                    # If we reach here and it's the last retry, accept what we have
                    if retry == max_retry_attempts - 1:
                        successful_regeneration = True
                        logger.info(f"⚠️ Using final attempt result for {post_id}")
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
                logger.info(f"✅ Using regenerated day node for {post_id}")
            else:
                # Fallback - merge with existing content
                existing = full_plan[platform_key][week_key].get(day_key, {})
                merged_node = {}
                if isinstance(existing, dict):
                    merged_node.update(existing)
                    
                # Try to get content from final_state_dict
                fallback_keys = (
                    "task", "content", "caption", "headline", "cta",
                    "hook", "angle", "hashtags", "title", "body", "notes"
                )
                for k in fallback_keys:
                    if k in final_state_dict:
                        merged_node[k] = final_state_dict[k]
                        
                logger.info(f"⚠️ Using fallback merging for {post_id}")

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
                "temperature_used": temperature,
                "new_content_preview": merged_node.get("content", "")[:100] + "..." if merged_node.get("content") else "No content"
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

        # Add metadata from stored plan (state_dict first, then stored_plan_full, then defaults)
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
                "enhanced_seed_generation": True,
                "improved_content_extraction": True,
                "fixed_regeneration_routing": True
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
            # store the whole response into approved_plan_v{n} if v1..v3
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



# COMPLETE FIXED src/agent/campaign_agent/social_media_agents.py

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

# Templates for task and content
TASK_PROMPT_TEMPLATE = TASK_DESCRIPTION_GENERATION_PROMPT

CONTENT_PROMPT_TEMPLATES = {
    "instagram": INSTAGRAM_CONTENT_GENERATION_PROMPT,
    "facebook": FACEBOOK_CONTENT_GENERATION_PROMPT,
    "x": X_CONTENT_GENERATION_PROMPT,
    "whatsapp": WHATSAPP_CONTENT_GENERATION_PROMPT,
    "email": EMAIL_CONTENT_GENERATION_PROMPT,
    "sms": SMS_CONTENT_GENERATION_PROMPT,
}

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
    current_post_id = state.get("current_post_id", "")
    
    lines = [
        f"--- REGENERATION ATTEMPT {attempt} FOR POST {current_post_id} (MUST BE DISTINCTLY DIFFERENT) ---"
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
    prompt = TASK_PROMPT_TEMPLATE.format(
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
    """
    ENHANCED social media post creator with better regeneration support and content extraction.
    """
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    current_post_id = state.get("current_post_id", "")
    is_regeneration = state.get("is_regeneration", False)
    
    print(f"🎯 Creating {platform} post - Day {current_day}, Regeneration: {is_regeneration}, Post ID: '{current_post_id}'")
    
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
    
    # Add human feedback if present (for regenerations)
    human_feedback = state.get("human_feedback_text", "")
    if human_feedback:
        regen_attempt = state.get("regen_attempt_number", 1)
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post and ensure the new version is distinctly different."
        print(f"🔄 Incorporating human feedback for {platform}: '{human_feedback}'")
    
    # Apply enhanced variation for regenerations
    regen_attempt = state.get("regen_attempt_number", 1)
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)
        print(f"🔄 Enhanced prompt for regeneration attempt {regen_attempt}")
    
    # Get dynamic temperature
    temperature = get_dynamic_temperature(state)
    
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
    for retry in range(3):  # Retry up to 3 times if too similar
        try:
            content = call_bedrock_for_text(
                prompt=base_content_prompt,
                max_tokens=max_tokens,
                temperature=temperature + (retry * 0.05)  # Slight boost per retry
            )
            if check_content_variation(content, previous_variants):
                print(f"✅ Generated unique content for {platform} (retry {retry})")
                break
            else:
                print(f"⚠️ Content too similar, retrying for {platform} (retry {retry})")
        except Exception as e:
            content = f"Error generating {platform} content: {str(e)}"
            print(f"❌ Error generating content for {platform}: {e}")
            break
    else:
        content += " [NOTE: Variation retry limit reached; content may be similar]"

    # Build post response with ENHANCED structure for better extraction
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
            "generation_timestamp": time.time(),
            "post_id": current_post_id
        }
    }
    
    # CRITICAL: Return both structured post AND direct content access
    response = {
        post_key: post,
        "messages": [f"Enhanced {platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f} using AWS Bedrock"],
        "current_step": f"create_{platform}_post",
        "content": content,  # DIRECT content access for extraction
        "task_description": task_description,  # DIRECT task access for extraction
        "task": task_description,  # Alternative key for task
        "regeneration_success": True,
        "platform": platform,
        "post_id": current_post_id
    }
    
    # For regenerations, ALSO return a simplified campaign_plan structure
    if is_regeneration and current_post_id:
        try:
            # Parse post_id to build structure: email_week_1_Day_1
            parts = current_post_id.split('_')
            if len(parts) >= 3:
                platform_key = parts[0]
                week_key = f"{parts[1]}_{parts[2]}"
                day_key = '_'.join(parts[3:]) if len(parts) > 3 else 'Day_1'
                
                campaign_plan = {
                    platform_key: {
                        week_key: {
                            day_key: {
                                "task": task_description,
                                "content": content,
                                "human_feedback": human_feedback,
                                "regeneration_count": regen_attempt,
                                "feedback_strength": state.get("feedback_strength", "medium"),
                                "temperature_used": temperature
                            }
                        }
                    }
                }
                response["campaign_plan"] = campaign_plan
                print(f"✅ Built campaign_plan structure for {current_post_id}")
        except Exception as e:
            print(f"⚠️ Failed to build campaign_plan structure: {e}")
    
    print(f"🎯 {platform} post creation completed - Content length: {len(content)} chars")
    return response

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """
    ENHANCED supervisor agent with better debugging for regeneration mode.
    """
    current_post_id = state.get("current_post_id", "")
    is_regeneration = state.get("is_regeneration", False)
    
    print(f"👥 Social Media Supervisor - Regeneration: {is_regeneration}, Post ID: '{current_post_id}'")
    
    return {
        "messages": ["Social media agents supervisor initialized"],
        "current_step": "social_media_agents_supervisor",
        "is_regeneration": is_regeneration,
        "current_post_id": current_post_id
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
