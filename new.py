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

def log_generation_info(state: State, platform: str) -> None:
    """Log basic information about content generation."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
    feedback = state.get("human_feedback_text", "")
    attempt = state.get("regen_attempt_number", 0)
    
    print(f"🔍 {platform} agent:")
    print(f"   regeneration_mode: {is_regen}")
    print(f"   post_id: {post_id}")
    print(f"   attempt_number: {attempt}")
    print(f"   has_feedback: {bool(feedback)}")
    if feedback:
        print(f"   feedback_preview: {feedback[:50]}...")

def calculate_temperature(state: State) -> float:
    """Calculate generation temperature based on feedback and attempt number."""
    strength = state.get("feedback_strength", "medium")
    attempt = state.get("regen_attempt_number", 1)
    base_temps = {"light": 0.75, "medium": 0.80, "strong": 0.85}
    base_temp = base_temps.get(strength, 0.80)
    
    if attempt == 1:
        return base_temp
    elif attempt == 2:
        return min(base_temp + 0.15, 0.95)
    else:  # 3rd+ attempt
        return min(base_temp + 0.25, 1.0)

def add_variation_instructions(prompt: str, state: State) -> str:
    """Add variation instructions for content regeneration."""
    attempt = state.get("regen_attempt_number", 1)
    lines = [
        f"--- REGENERATION ATTEMPT {attempt} (MUST BE DIFFERENT) ---"
    ]
    
    strength = state.get("feedback_strength", "medium")
    if strength == "strong":
        lines.append("IMPORTANT: Completely rewrite with new structure and approach.")
    elif strength == "medium":
        lines.append("IMPORTANT: Substantially change content and messaging.")
    else:
        lines.append("IMPORTANT: Improve content with fresh ideas.")
    
    if state.get("previous_variants"):
        prev_count = len(state['previous_variants'])
        lines.append(f"AVOID similarity to the last {prev_count} versions.")
    
    if state.get("force_variation", False):
        lines.append("VARIATION REQUIRED: Output must differ in style and tone.")
    
    # Add uniqueness seed
    uniqueness_seed = f"Generation seed: {time.time()} | Focus: {random.choice(['creative', 'innovative', 'fresh', 'bold'])}"
    lines.append(uniqueness_seed)
    
    return prompt + "\n\n" + "\n".join(lines)

def create_task_description(state: State, phase: str, day_context: str) -> str:
    """Generate task description for the content."""
    prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=state.get("campaign_objective", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        day_context=day_context
    )
    
    temp = calculate_temperature(state) * 0.90
    try:
        desc = call_bedrock_for_text(prompt, max_tokens=50, temperature=temp).strip()
        if not desc:
            desc = call_bedrock_for_text(prompt, max_tokens=40, temperature=temp + 0.10).strip()
        return desc if len(desc) <= 80 else desc[:77] + "..."
    except Exception:
        return f"Generate content for {state.get('campaign_objective', '').lower()}"

def is_content_different(new_content: str, previous_variants: list) -> bool:
    """Check if new content is sufficiently different from previous versions."""
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
    """Create social media post content for specified platform."""
    
    # Log generation info
    log_generation_info(state, platform)
    
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
        1: "This is the opening content piece",
        2: "This is the follow-up content piece",
        3: "This builds momentum from previous content"
    }
    day_context = day_context_map.get(current_day, f"This continues the {phase} phase")
    
    # Create task description
    task_description = create_task_description(state, phase, day_context)
    
    # Build content prompt
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
    
    # Add human feedback if present
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)
    
    if human_feedback:
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\n"
        base_content_prompt += "IMPORTANT: Incorporate this feedback and make the content different from the previous version."
    
    # Apply variation instructions for regenerations
    if regen_attempt > 1:
        base_content_prompt = add_variation_instructions(base_content_prompt, state)
        print(f"🔄 Added variation instructions for attempt {regen_attempt}")
    
    # Get temperature
    temperature = calculate_temperature(state)
    print(f"🌡️ Using temperature: {temperature} for attempt {regen_attempt}")
    
    # Platform-specific token limits
    max_tokens_map = {
        "instagram": 1000,
        "facebook": 1000,
        "x": 500,
        "whatsapp": 800,
        "email": 1200,
        "sms": 300
    }
    max_tokens = max_tokens_map.get(platform, 1000)
    
    # Generate content with variation checking
    previous_variants = state.get("previous_variants", [])
    content = ""
    
    for retry in range(3):  # Retry up to 3 times if too similar
        try:
            print(f"🎯 Generating content for {platform} (retry {retry})")
            content = call_bedrock_for_text(
                prompt=base_content_prompt,
                max_tokens=max_tokens,
                temperature=temperature + (retry * 0.05)
            )
            
            if content and content.strip():
                if is_content_different(content, previous_variants):
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
        content += " [NOTE: Retry limit reached; content may be similar]"
        print(f"⚠️ Retry limit reached for {platform}")
    
    # Build post response
    post_key = f"{platform}_post"
    post = {
        "task_description": task_description,
        "content": content,
        "generation_info": {
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
        "messages": [f"{platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f}"],
        "current_step": f"create_{platform}_post",
        "content": content,  # Direct content access
        "task_description": task_description  # Direct task access
    }

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """Coordinate social media content generation."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
    
    print(f"🎭 Social Media Supervisor:")
    print(f"   regeneration_mode: {is_regen}")
    print(f"   current_post_id: {post_id}")
    
    return {
        "messages": ["Social media supervisor initialized"],
        "current_step": "social_media_agents_supervisor"
    }

# Platform-specific functions
def create_instagram_post(state: State) -> Dict[str, Any]:
    """Create Instagram post content."""
    return create_social_media_post(state, "instagram")

def create_facebook_post(state: State) -> Dict[str, Any]:
    """Create Facebook post content."""
    return create_social_media_post(state, "facebook")

def create_x_post(state: State) -> Dict[str, Any]:
    """Create X (Twitter) post content."""
    return create_social_media_post(state, "x")

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    """Create WhatsApp message content."""
    return create_social_media_post(state, "whatsapp")

def create_email_post(state: State) -> Dict[str, Any]:
    """Create email content."""
    return create_social_media_post(state, "email")

def create_sms_post(state: State) -> Dict[str, Any]:
    """Create SMS content."""
    return create_social_media_post(state, "sms")



# Helper functions for feedback API (extract these to a separate module or place above the API)

import copy
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any
from fastapi import HTTPException
from utils.logger import logger

def classify_feedback_strength(feedback_text: str) -> str:
    """Classify the strength of feedback based on keywords."""
    feedback_lower = feedback_text.lower()
    strong_indicators = ["completely rewrite", "totally different", "start over", "completely change"]
    medium_indicators = ["improve", "enhance", "better", "more", "add", "include"]
    
    if any(indicator in feedback_lower for indicator in strong_indicators):
        return "strong"
    elif any(indicator in feedback_lower for indicator in medium_indicators):
        return "medium"
    else:
        return "light"

def calculate_progressive_temperature(attempt_number: int, feedback_strength: str) -> float:
    """Calculate temperature based on attempt number and feedback strength."""
    base_temps = {"light": 0.8, "medium": 0.85, "strong": 0.9}
    base_temp = base_temps.get(feedback_strength, 0.8)
    
    if attempt_number == 1:
        return base_temp
    elif attempt_number == 2:
        return min(base_temp + 0.1, 0.95)
    else:
        return 0.95

def generate_content_seed(post_id: str, attempt_number: int, feedback_text: str) -> str:
    """Generate unique seed for content generation."""
    timestamp = datetime.utcnow().isoformat()
    seed_input = f"{post_id}|{attempt_number}|{feedback_text[:50]}|{timestamp}"
    return hashlib.sha256(seed_input.encode()).hexdigest()

def check_content_similarity(new_content: str, previous_variants: List[Dict]) -> bool:
    """Check if new content is sufficiently different from previous variants."""
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

def validate_post_exists(post_id: str, full_plan: Dict) -> tuple:
    """Validate that post exists in campaign plan and return parsed components."""
    parts = post_id.split('_')
    if len(parts) >= 3:
        platform_key = parts[0]
        week_key = f"{parts[1]}_{parts[2]}"
        day_key = '_'.join(parts[3:]) if len(parts) > 3 else 'Day_1'
    else:
        return None, None, None, False
    
    try:
        exists = (platform_key and
                 platform_key in full_plan and
                 isinstance(full_plan[platform_key], dict) and
                 week_key in full_plan[platform_key] and
                 isinstance(full_plan[platform_key][week_key], dict) and
                 day_key in full_plan[platform_key][week_key])
        return platform_key, week_key, day_key, exists
    except Exception:
        return platform_key, week_key, day_key, False

def prepare_regeneration_state(state_dict: Dict, feedback_dict: Dict, post_id: str, 
                              fb_text: str, version_number: int, feedback_strength: str,
                              temperature: float, enhanced_seed: str, previous_variants: List) -> Dict:
    """Prepare state for content regeneration."""
    return {
        **state_dict,
        "stage": "content_generation",
        "plan_approved": True,
        "campaign_plan": state_dict.get("campaign_plan"),
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

def extract_regenerated_content(final_state_dict: Dict, platform_key: str, week_key: str, day_key: str) -> str:
    """Extract regenerated content from agent response."""
    # First try direct content extraction
    new_content = final_state_dict.get("content", "")
    
    # Try platform-specific key if direct content not found
    if not new_content:
        platform_post_key = f"{platform_key}_post"
        platform_post = final_state_dict.get(platform_post_key, {})
        if isinstance(platform_post, dict):
            new_content = platform_post.get("content", "")
    
    # Try campaign plan structure if still no content
    if not new_content:
        agent_plan = final_state_dict.get("campaign_plan")
        if isinstance(agent_plan, dict):
            try:
                new_day_node = agent_plan.get(platform_key, {}).get(week_key, {}).get(day_key)
                if isinstance(new_day_node, dict):
                    new_content = new_day_node.get("content", "")
            except Exception:
                pass
    
    return new_content

def create_merged_node(existing_node: Dict, new_content: str, final_state_dict: Dict, 
                      fb_text: str, version_number: int, feedback_strength: str, temperature: float) -> Dict:
    """Create merged node with new content and metadata."""
    if isinstance(existing_node, dict):
        merged_node = copy.deepcopy(existing_node)
    else:
        merged_node = {}
    
    # Update with new content
    merged_node["content"] = new_content
    
    # Get task description if available
    task_description = final_state_dict.get("task_description")
    if task_description:
        merged_node["task"] = task_description
    
    # Add regeneration metadata - FIXED: Use the correct field name
    merged_node["human_feedback"] = fb_text
    merged_node["regenration_count"] = version_number  # Note: keeping original typo for consistency
    merged_node["feedback_strength"] = feedback_strength
    merged_node["temperature_used"] = temperature
    
    # Clean up image-related fields
    image_related_keys = ["image_path_s3", "image_paths", "image_urls", "images", "image_prompt"]
    for img_key in image_related_keys:
        if img_key in merged_node:
            merged_node[img_key] = []
    
    return merged_node

def store_content_variant(feedback_dict: Dict, pid_norm: str, merged_node: Dict, temperature: float, version_number: int) -> None:
    """Store content variant for future similarity checking."""
    pv_map = feedback_dict.setdefault("previous_variants", {})
    pv_list = pv_map.get(pid_norm, [])
    
    variant_snapshot = {
        "content": merged_node.get("content", ""),
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

# SHORTENED FEEDBACK API
@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Process feedback and regenerate content with shorter, cleaner implementation.
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing feedback for {campaign_full_name}")
        
        # Basic validations
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
        
        # Load campaign data from database
        planner_record = get_agentic_planner_record(username=username, campaign_name=campaign_name)
        if not planner_record:
            raise HTTPException(status_code=404, detail=f"No planner record found for '{campaign_full_name}'")
        
        # Load campaign plan
        stored_plan_full = None
        campaign_plan = None
        
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
        
        # Load feedback tracking
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
        
        # Load state data
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
        
        # Check max attempts for all posts
        current_regen_attempts = feedback_dict.get("current_regen_attempts", {})
        max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)
        
        for fb in deduped_feedbacks:
            pid_norm = fb.post_id.lower()
            current_attempts = current_regen_attempts.get(pid_norm, 0)
            if current_attempts >= max_regen_attempts:
                raise HTTPException(status_code=400, detail=f"Max regeneration attempts reached for post_id '{fb.post_id}'")
        
        version_number = 0
        processed_post_ids: List[str] = []
        
        # Process each feedback
        for fb in deduped_feedbacks:
            post_id = (fb.post_id or "").strip()
            pid_norm = post_id.lower()
            fb_text = (fb.feedback_text or "").strip()
            
            # Validate post exists
            platform_key, week_key, day_key, exists = validate_post_exists(post_id, full_plan)
            if not exists:
                details[post_id] = {"success": False, "message": f"Post ID '{post_id}' not found in campaign plan."}
                continue
            
            # Check attempt limits
            current_attempts = current_regen_attempts.get(pid_norm, 0)
            if current_attempts >= max_regen_attempts:
                details[post_id] = {
                    "success": False,
                    "message": f"Maximum regeneration attempts ({max_regen_attempts}) reached for '{post_id}'",
                    "regeneration_attempts": current_attempts
                }
                continue
            
            # Record feedback and increment attempts
            current_attempts += 1  # FIXED: Increment the attempt counter
            current_regen_attempts[pid_norm] = current_attempts  # FIXED: Store incremented value
            feedback_dict["current_regen_attempts"] = current_regen_attempts
            
            feedback_dict.setdefault("feedback_history", []).append({
                "post_id": post_id,
                "timestamp": datetime.utcnow().isoformat(),
                "feedback_text": fb_text,
                "regen_attempt_number": current_attempts,
                "feedback_strength": classify_feedback_strength(fb_text)
            })
            
            human_feedback_map[post_id] = fb_text
            version_number = current_attempts  # FIXED: Use the correct incremented value
            processed_post_ids.append(post_id)
            
            # Prepare regeneration parameters
            feedback_strength = classify_feedback_strength(fb_text)
            temperature = calculate_progressive_temperature(version_number, feedback_strength)
            content_seed = generate_content_seed(post_id, version_number, fb_text)
            previous_variants = feedback_dict.get("previous_variants", {}).get(pid_norm, [])
            
            # Prepare regeneration state
            state_input = prepare_regeneration_state(
                state_dict, feedback_dict, post_id, fb_text, version_number,
                feedback_strength, temperature, content_seed, previous_variants
            )
            
            # Attempt content regeneration with retries
            max_retry_attempts = 3
            successful_regeneration = False
            new_content = ""
            
            for retry in range(max_retry_attempts):
                try:
                    if retry > 0:
                        state_input["random_seed"] = f"{content_seed}_retry_{retry}"
                        state_input["temperature_override"] = min(temperature + (retry * 0.02), 0.98)
                    
                    final_state = await system_agents.ainvoke(state_input)
                    final_state_dict = dict(final_state)
                    
                    # Extract content from agent response
                    new_content = extract_regenerated_content(final_state_dict, platform_key, week_key, day_key)
                    
                    if new_content and new_content.strip():
                        if check_content_similarity(new_content, previous_variants):
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
            
            # Merge regenerated content
            existing_node = full_plan[platform_key][week_key].get(day_key, {})
            merged_node = create_merged_node(
                existing_node, new_content, final_state_dict, fb_text, 
                version_number, feedback_strength, temperature
            )
            
            # Update the full plan
            full_plan[platform_key][week_key][day_key] = merged_node
            
            # Store variant for future similarity checking
            store_content_variant(feedback_dict, pid_norm, merged_node, temperature, version_number)
            
            details[post_id] = {
                "success": True,
                "message": "Feedback processed and post regenerated successfully",
                "regeneration_attempts": version_number,  # FIXED: Use correct version number
                "feedback_strength": feedback_strength,
                "temperature_used": temperature
            }
            
            logger.info(f"Successfully processed feedback for {post_id}: New content length = {len(new_content)}")
        
        # Generate response
        processed_count = len([k for k, v in details.items() if v.get("success")])
        all_attempts = feedback_dict.get("current_regen_attempts", {}) or {}
        
        # Calculate batch version
        status = get_campaign_status(username, campaign_name)
        existing_versions = sum([
            status["has_approved_plan_v1"],
            status["has_approved_plan_v2"], 
            status["has_approved_plan_v3"]
        ])
        batch_version = existing_versions + 1
        
        if batch_version > 3:
            raise HTTPException(status_code=400, detail="Maximum feedback versions (3) reached for this campaign")
        
        # Build final response data
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
        
        # Generate and upload Excel
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
            "message": f"Feedback processing completed for {processed_count} of {len(deduped_feedbacks)} posts.",
            "campaign_plan": approved_plan_data["campaign_plan"],
            "platforms": approved_plan_data.get("platforms", []),
            "generated_images": [],
            "image_generation_status": "disabled",
            "excel_s3_url": excel_s3_url,
            "processed": len(deduped_feedbacks),
            "batch_version": batch_version,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
            "features": {
                "progressive_temperature": True,
                "content_similarity_checking": True,
                "feedback_strength_classification": True,
                "content_seed_generation": True
            }
        }
        
        # Update database
        try:
            total_regenerations = sum(all_attempts.values())  # FIXED: This will now show correct cumulative count
            fields_to_update = {
                "feedback_response": json.dumps({
                    "feedback": feedback_dict,
                    "approved_plan": approved_plan_data,
                    "details": details,
                    "features": response["features"]
                }, ensure_ascii=False),
                "regenration_count": total_regenerations  # FIXED: Cumulative count across all posts
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
        logger.error(f"Unexpected error in submit_feedback: {e}")
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")


# src/campaign_agent/system_agents.py

from typing import Dict, Any, List
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from src.models import State
from src.vectorDB import hybrid_search
from src.llm.bedrock import call_bedrock_for_text
from .social_media_agents import (
    create_instagram_post, create_facebook_post, create_x_post,
    create_whatsapp_post, create_email_post, create_sms_post
)

# Mapping from platform name to agent function
PLATFORM_AGENT_MAP = {
    "instagram": create_instagram_post,
    "facebook": create_facebook_post,
    "x": create_x_post,
    "whatsapp": create_whatsapp_post,
    "email": create_email_post,
    "sms": create_sms_post
}

def orchestrator_agent(state: State) -> Dict[str, Any]:
    """
    Main orchestrator agent with improved debugging for regeneration mode.
    """
    is_regen = state.get("is_regeneration", False)
    plan_approved = state.get("plan_approved", False)
    stage = state.get("stage", "plan_generation")
    current_post_id = state.get("current_post_id", "")
    
    print(f"🎭 Orchestrator Agent Debug:")
    print(f"   is_regeneration: {is_regen}")
    print(f"   plan_approved: {plan_approved}")
    print(f"   stage: {stage}")
    print(f"   current_post_id: {current_post_id}")
    
    if is_regen and current_post_id:
        return {
            "messages": [f"Orchestrator: Regeneration mode for {current_post_id}"],
            "current_step": "orchestrator_agent",
            "stage": "regeneration",
            "is_regeneration": True,
            "current_post_id": current_post_id
        }
    elif plan_approved and stage == "content_generation":
        return {
            "messages": ["Orchestrator: Starting content generation phase"],
            "current_step": "orchestrator_agent",
            "stage": "content_generation"
        }
    else:
        return {
            "messages": ["Orchestrator: Starting campaign plan generation"],
            "current_step": "orchestrator_agent",
            "stage": "plan_generation"
        }

def system_agent_orchestrator(state: State) -> Dict[str, Any]:
    """
    System agent orchestrator that manages system-level tasks.
    """
    return {
        "messages": ["System agent orchestrator initialized"],
        "current_step": "system_agent_orchestrator"
    }

def prompt_optimization(state: State) -> Dict[str, Any]:
    """
    Prompt optimization agent that optimizes prompts for content generation using vector database context.
    Uses hybrid search to retrieve relevant context directly from the vector database.
    """
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")
    target_audience_location = state.get("target_audience_location", "")
    collection_name = state.get("collection_name", "default_collection")
    
    # Base prompt elements
    base_prompt_elements = {
        "objective": campaign_objective,
        "description": campaign_description,
        "audience": target_audience,
        "audience_location": target_audience_location,
        "theme": state.get("campaign_theme"),
        "location": state.get("target_location", "Global")
    }
    
    # Enhanced prompt elements using vector database and web search context
    improved_prompt_elements = base_prompt_elements.copy()
    
    # Get web search results from state
    web_search_results = state.get("search_results", "")
    
    # Create search query from campaign parameters
    search_query = f"{campaign_objective} {campaign_description} {target_audience} campaign strategy content"

    try:
        # Use hybrid search to get relevant context
        search_result = hybrid_search(
            query=search_query,
            collection_name=collection_name,
            n_results=5
        )
        
        if search_result.get("success") and search_result.get("results"):
            context_results = search_result["results"]
            context_insights = [result["text"] for result in context_results if result.get("text")]
            context_sources = [result["metadata"].get("source", "unknown") for result in context_results]
            
            context_keywords = []
            
            # Analyze context insights for relevant keywords and themes
            for insight in context_insights[:5]:  # Use top 5 insights
                words = insight.lower().split()
                relevant_terms = [word for word in words if len(word) > 4 and
                                  any(keyword in word for keyword in ['campaign', 'brand', 'message', 'content', 'audience', 'strategy'])]
                context_keywords.extend(relevant_terms[:2])  # Limit keywords per insight
            
            # Remove duplicates and limit total keywords
            context_keywords = list(set(context_keywords))[:10]
            
            # Improve prompt elements with context
            if context_keywords:
                improved_prompt_elements["context_keywords"] = context_keywords
            
            if web_search_results:
                improved_prompt_elements["web_search_results"] = web_search_results
            
            if context_sources:
                improved_prompt_elements["reference_sources"] = list(set(context_sources))[:3]  # Top 3 unique sources
            
            # Create context-aware prompt guidance
            context_guidance = f"Incorporate insights from {len(context_insights)} relevant context sources and web search results"
            if context_keywords:
                context_guidance += f", focusing on themes related to: {', '.join(context_keywords[:5])}"
            
            improved_prompt_elements["context_guidance"] = context_guidance
            improved_prompt_elements["context_insights"] = context_insights[:3]  # Store top 3 insights
            
            messages = [
                "Prompt optimization completed with vector database and web search context integration",
                f"Improved prompts with {len(context_insights)} context insights from {len(set(context_sources))} sources and web search results",
                f"Extracted {len(context_keywords)} relevant keywords for content focus"
            ]
            context_improved = True
        else:
            # Fallback when no context is available
            improved_prompt_elements["context_guidance"] = "Using campaign parameters only - no relevant context found in vector database"
            if web_search_results:
                improved_prompt_elements["web_search_results"] = web_search_results
            messages = [
                "Prompt optimization completed using campaign parameters and web search results only",
                "No relevant context found in vector database - using standard optimization approach with web search"
            ]
            context_improved = False
            
    except Exception as e:
        # Handle any errors with hybrid search
        improved_prompt_elements["context_guidance"] = "Using campaign parameters only - error accessing vector database"
        messages = [
            "Prompt optimization completed using campaign parameters only",
            f"Error accessing vector database: {str(e)} - using standard optimization approach"
        ]
        context_improved = False
    
    return {
        "messages": messages,
        "current_step": "prompt_optimization",
        "optimized_prompts": improved_prompt_elements,
        "context_improved": context_improved
    }

def text_generator(state: State) -> Dict[str, Any]:
    """
    Text generation agent that creates text content.
    """
    optimized_prompts = state.get("optimized_prompts", {})
    
    # Create a detailed prompt for the LLM
    prompt = f"""Generate content based on the following:
    
    Objective: {optimized_prompts.get('objective')}
    Description: {optimized_prompts.get('description')}
    Audience: {optimized_prompts.get('audience')}
    Audience Location: {optimized_prompts.get('audience_location')}
    Theme: {optimized_prompts.get('theme')}
    Location: {optimized_prompts.get('location')}
    Context Guidance: {optimized_prompts.get('context_guidance')}
    Context Keywords: {', '.join(optimized_prompts.get('context_keywords', [])) if isinstance(optimized_prompts.get('context_keywords'), list) else optimized_prompts.get('context_keywords', '')}
    Web Search Results: {optimized_prompts.get('web_search_results')}
    """
    
    generated_text = call_bedrock_for_text(
        prompt=prompt,
        max_tokens=2000,
        temperature=0.7
    )
    
    return {
        "messages": ["Text generation completed using AWS Bedrock"],
        "current_step": "text_generator",
        "generated_text": generated_text
    }

def content_reviewer(state: State) -> Dict[str, Any]:
    """
    Content review agent that reviews generated content.
    """
    return {
        "messages": ["Content review completed - no image generation"],
        "current_step": "content_reviewer"
    }

def content_formatter(state: State) -> Dict[str, Any]:
    """
    Content formatting agent that formats content for different platforms.
    """
    return {
        "messages": ["Content formatting completed"],
        "current_step": "content_formatter"
    }

def plan_generator(state: State) -> Dict[str, Any]:
    """
    Plan generator agent that creates the initial campaign plan structure with AI-generated tasks.
    This runs in stage 1 to generate the basic plan outline for approval.
    """
    base_plan = state.get("base_plan_dict", {})
    platforms = state.get("platforms", ["instagram", "facebook", "x", "whatsapp", "email", "sms"])
    
    # Create correct structure - platform -> week -> day
    campaign_plan = {}
    
    for platform in platforms:
        campaign_plan[platform] = {}  # Each platform at root level
        
        for week_key, week_data in base_plan.items():
            # Use proper week naming (week_1, week_2, etc.)
            week_num = f"week_{week_key.split('_')[-1]}" if '_' in week_key else f"week_1"
            campaign_plan[platform][week_num] = {}
            
            for day_index, day_info in enumerate(week_data):
                day_key = f"Day_{day_index + 1}"
                agent_f = PLATFORM_AGENT_MAP.get(platform)
                
                if agent_f:
                    agent_state = state.copy()
                    agent_state["current_day"] = day_index + 1
                    agent_state["total_days"] = len(week_data)
                    # Ensure no image generation
                    agent_state["generate_images"] = False
                    agent_state["image_generation_enabled"] = False
                    try:
                        result = agent_f(agent_state)
                        post = result.get(f"{platform}_post")
                        task_description = post.get('task_description') if post else f"AI-generated content for {platform}"
                        
                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description,
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"Error generating task: {str(e)}",
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No agent found for {platform}",
                        "human_feedback": "",
                        "regeneration_count": 0
                    }
    
    return {
        "messages": ["Campaign plan outline generated - awaiting approval (no images)"],
        "current_step": "plan_generator",
        "campaign_plan": campaign_plan,
        "stage": "plan_generation"
    }

def content_validator(state: State) -> Dict[str, Any]:
    """
    Content validation agent that generates full content after approval using AI agents.
    This runs in stage 2 to generate complete AI-powered campaign content.
    """
    base_plan = state.get("base_plan_dict", {})
    platforms = state.get("platforms", ["instagram", "facebook", "x", "whatsapp", "email", "sms"])
    campaign_theme = state.get("campaign_theme")

    campaign_plan: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # Resolve platform agent map safely
    platform_agent_map = state.get("PLATFORM_AGENT_MAP")
    if not isinstance(platform_agent_map, dict):
        platform_agent_map = globals().get("PLATFORM_AGENT_MAP", {}) if isinstance(globals().get("PLATFORM_AGENT_MAP", {}), dict) else {}

    for platform in platforms:
        campaign_plan[platform] = {}

        for week_key, week_data in base_plan.items():
            week_num = f"week_{week_key.split('_')[-1]}" if isinstance(week_key, str) and "_" in week_key else "week_1"
            if week_num not in campaign_plan[platform]:
                campaign_plan[platform][week_num] = {}

            # Ensure week_data is iterable by days
            if isinstance(week_data, (list, tuple)):
                day_iter = list(enumerate(week_data, start=1))
            elif isinstance(week_data, dict):
                def _day_key(k: Any) -> Any:
                    try:
                        if isinstance(k, str) and k.lower().startswith("day_"):
                            return int(k.split("_")[-1])
                    except Exception:
                        pass
                    return k
                day_iter = [(k if isinstance(k, int) else k, v) for k, v in sorted(week_data.items(), key=lambda kv: _day_key(kv[0]))]
            else:
                day_iter = []

            for day_idx_or_key, day_info in day_iter:
                if isinstance(day_idx_or_key, int):
                    day_index = day_idx_or_key
                    day_key = f"Day_{day_index}"
                else:
                    day_key = str(day_idx_or_key)
                    try:
                        day_index = int(day_key.split("_")[-1])
                    except Exception:
                        day_index = 1

                agent_f = platform_agent_map.get(platform)
                
                if agent_f:
                    # Build agent state - no image generation
                    agent_state = dict(state)
                    agent_state.update({
                        "platform": platform,
                        "current_week": week_num,
                        "current_day": day_index,
                        "total_days": len(day_iter),
                        "day_info": day_info,
                        "campaign_theme": campaign_theme,
                        "generate_images": False,
                        "image_generation_enabled": False
                    })

                    try:
                        result = agent_f(agent_state) or {}
                        if not isinstance(result, dict):
                            result = {"result": result}

                        # Flexible extraction of post payload
                        post = (
                            result.get(f"{platform}_post")
                            or result.get("post")
                            or result.get("data")
                            or result
                        )

                        # Default task and content
                        task_description = f"AI-generated {platform} content for day {day_index}"
                        content_text = ""

                        if isinstance(post, dict):
                            content_text = str(post.get("content") or post.get("text") or post.get("body") or "")
                            task_description = str(post.get("task_description") or task_description)
                        else:
                            content_text = "" if post is None else str(post)

                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description,
                            "content": content_text,
                            "human_feedback": "",
                            "regeneration_count": 0
                        }

                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"AI generation error for {platform}",
                            "content": f"Error generating content: {e}",
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No AI agent found for {platform}",
                        "content": f"Platform {platform} not supported",
                        "human_feedback": "",
                        "regeneration_count": 0
                    }

    return {
        "messages": [f"AI-powered content generated for '{campaign_theme or 'campaign'}' using AWS Bedrock (no images)"],
        "current_step": "content_validator",
        "campaign_plan": campaign_plan
    }

@tool
def web_search_tool(query: str) -> str:
    """
    Web search tool for finding relevant information.
    
    Args:
        query: The search query
        
    Returns:
        Search results as a string
    """
    search = DuckDuckGoSearchRun()
    return search.run(query)



INSTAGRAM_CONTENT_GENERATION_PROMPT = """
Create a professional Instagram post for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Instagram Requirements:
  - Professional tone, no emojis
  - 5–8 relevant hashtags at end
  - Strong first‐line hook
  - Clear business call‐to‐action
  - ~170 words (±5%)
  - Mobile‐friendly formatting
Generate a detailed caption that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

FACEBOOK_CONTENT_GENERATION_PROMPT = """
Create a strategic Facebook post for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Facebook Requirements:
  - Professional tone, no emojis
  - Long‐form narrative for thought leadership
  - Authoritative language
  - Clear business call‐to‐action
  - ~170 words (±5%)
Generate an authoritative post that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

X_CONTENT_GENERATION_PROMPT = """
Create a strategic X (Twitter) post for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
X Requirements:
  - Professional tone, no emojis
  - 2–3 business hashtags
  - Direct, authoritative language
  - 280‐character limit
Generate an insightful X post that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

WHATSAPP_CONTENT_GENERATION_PROMPT = """
Create a strategic WhatsApp message for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
WhatsApp Requirements:
  - Professional conversational tone, no emojis
  - Clear business call‐to‐action or link
  - ≤170 characters
Generate a concise message that builds professional rapport and drives {campaign_objective} with {target_audience} in {target_audience_location}.
"""

EMAIL_CONTENT_GENERATION_PROMPT = """
Create a strategic email for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Email Requirements:
  - Professional subject line
  - Formal tone, no emojis
  - Personalized greeting
  - 250–300 words
  - Clear business call‐to‐action
  - Proper email structure
Generate a compelling email that highlights ROI and resonates with {target_audience} in {target_audience_location}, driving {campaign_objective}.
"""

SMS_CONTENT_GENERATION_PROMPT = """
Create a strategic SMS for Day {current_day} of a {total_days}-day campaign:
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
SMS Requirements:
  - Professional tone, no emojis
  - Include link or CTA
  - Sense of business urgency
  - ≤100 characters
  - Opt‐out compliance
Generate a concise SMS that delivers immediate business value to {target_audience} in {target_audience_location} and drives {campaign_objective}.

