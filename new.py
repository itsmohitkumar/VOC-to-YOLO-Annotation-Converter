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

import sys
import os
import hashlib
import time
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.llm.bedrock import call_bedrock_for_text

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
    """Generic social media post creator with regeneration support."""
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
    
    # Add human feedback if present
    human_feedback = state.get("human_feedback_text", "")
    if human_feedback:
        regen_attempt = state.get("regen_attempt_number", 1)
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post and ensure the new version is distinctly different."
    
    # Apply enhanced variation for regenerations
    regen_attempt = state.get("regen_attempt_number", 1)
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)
    
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
                break
        except Exception as e:
            content = f"Error generating {platform} content: {str(e)}"
            break
    else:
        content += " [NOTE: Variation retry limit reached; content may be similar]"

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
    
    return {
        post_key: post,
        "messages": [f"Enhanced {platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f} using AWS Bedrock"],
        "current_step": f"create_{platform}_post",
        "content": content,  # Direct content access for state extraction
        "task_description": task_description  # Direct task access for state extraction
    }

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """Supervisor agent that coordinates social media content generation."""
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

import time

# ------------------------ BUILD GRAPH ------------------------
graph = StateGraph(State)

# ------------------------ SYSTEM AGENT NODES ------------------------
graph.add_node("orchestrator_agent", orchestrator_agent)
graph.add_node("system_agent_orchestrator", system_agent_orchestrator)

def web_search_agent(state: State) -> Dict[str, Any]:
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")
    search_query = f"{campaign_objective} {campaign_description} {target_audience} marketing campaign trends 2024"
    try:
        search_results = web_search_tool.invoke(search_query)
    except Exception:
        search_results = ""
    return {
        "messages": ["Web search completed"],
        "current_step": "web_search_agent",
        "search_results": search_results
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

# ------------------------ REGENERATION ROUTER ------------------------
def regeneration_router(state: State) -> str:
    if state.get("is_regeneration", False):
        post_id = state.get("current_post_id", "")
        attempts = state.get("current_regen_attempts", {}).get(post_id.lower(), 1)
        state["regen_attempt_number"] = attempts
        state["force_variation"] = True
        state["random_seed"] = f"{post_id}|{time.time()}"
        return "social_media_agents_supervisor"
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
    if state.get("stage") == "plan_generation":
        return "plan_generator"
    if state.get("stage") == "content_generation" and state.get("plan_approved", False):
        return "system_agent_orchestrator"
    return "plan_generator"

# ------------------------ STAGE 1 ------------------------
graph.add_edge("plan_generator", "__end__")

# ------------------------ STAGE 2 ------------------------
graph.add_edge("system_agent_orchestrator", "web_search_agent")
graph.add_edge("web_search_agent", "prompt_optimization")
graph.add_edge("prompt_optimization", "text_generator")
graph.add_edge("text_generator", "content_reviewer")
graph.add_edge("content_reviewer", "content_validator")

# ------------------------ STAGE 3 ------------------------
graph.add_edge("content_validator", "social_media_agents_supervisor")

def social_media_router(state: State) -> str:
    post_id = state.get("current_post_id", "")
    if post_id:
        plat = post_id.split("_")[0].lower()
        if plat in PLATFORM_AGENT_MAP:
            return f"create_{plat}_post"
        return "__end__"
    for p in ["instagram", "facebook", "x", "whatsapp", "email", "sms"]:
        if p in state.get("platforms", []):
            return f"create_{p}_post"
    return "create_instagram_post"

graph.add_conditional_edges(
    "social_media_agents_supervisor",
    social_media_router,
    ["create_instagram_post", "create_facebook_post", "create_x_post",
     "create_whatsapp_post", "create_email_post", "create_sms_post"]
)

# In regeneration mode, end after one platform agent
for p in ["instagram", "facebook", "x", "whatsapp", "email", "sms"]:
    graph.add_edge(f"create_{p}_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()




from typing import Dict, Any, List
from fastapi import HTTPException
from datetime import datetime
import hashlib
import random
import time
import json
from src.models import State
from src.agent.graph import system_agents
from src import get_user_by_username, get_user_campaigns, get_campaign_by_name, update_agentic_campaign_planner
from src.llm.bedrock import call_bedrock_for_text
from src.campaign_agent.excel_generator import generate_and_upload_combined_excel_to_s3
from utils.logger import logger

def classify_feedback_strength(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["rewrite", "completely"]):
        return "strong"
    if any(k in t for k in ["improve", "add", "include"]):
        return "medium"
    return "light"

def similarity_ok(new: str, prevs: List[Dict]) -> bool:
    if not prevs or not new:
        return True
    wnew = set(new.lower().split())
    for v in prevs[-2:]:
        wold = set(v.get("content","").lower().split())
        overlap = len(wnew & wold) / max(len(wnew), len(wold), 1)
        if overlap > 0.7:
            return False
    return True

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(username: str, campaign_name: str, feedback_request: Any) -> Dict[str, Any]:
    campaign_full = f"{username}/{campaign_name}"
    user = get_user_by_username(username) or HTTPException(404, "User not found")
    if campaign_name not in [c["campaign_name"] for c in get_user_campaigns(username)]:
        raise HTTPException(404, "Campaign not found")

    # Deduplicate
    seen = set()
    feedbacks = []
    for fb in feedback_request.feedbacks:
        pid = fb.post_id.strip()
        if pid.lower() not in seen:
            seen.add(pid.lower())
            feedbacks.append(fb)
    if not feedbacks:
        raise HTTPException(400, "No valid feedback items")

    # Load existing plan JSON from DB via get_campaign_by_name
    campaign_data = get_campaign_by_name(campaign_name, username) or {}
    stored = campaign_data.get("approved_plan") or campaign_data.get("plan_response") or {}
    if isinstance(stored, str):
        stored = json.loads(stored)
    plan = stored.get("campaign_plan", {})

    # Load existing feedback tracking from DB field
    fb_store = campaign_data.get("feedback_response")
    fb_dict = json.loads(fb_store) if fb_store else {
        "current_attempts": {}, "feedback_history": [], "previous_variants": {}
    }

    details = {}
    for fb in feedbacks:
        post_id = fb.post_id.strip()
        pid_norm = post_id.lower()
        text = fb.feedback_text.strip()
        # Validate existence
        parts = post_id.split("_")
        if len(parts) < 4 or parts[0] not in plan:
            details[post_id] = {"success": False, "message": "Invalid post_id"}
            continue

        attempts = fb_dict["current_attempts"].get(pid_norm, 0)
        if attempts >= 3:
            details[post_id] = {"success": False, "message": "Max attempts reached"}
            continue

        attempts += 1
        fb_dict["current_attempts"][pid_norm] = attempts
        fb_dict["feedback_history"].append({"post_id":post_id,"text":text,"attempt":attempts,"ts":datetime.utcnow().isoformat()})

        # Prepare state for regeneration
        state_input = {
            **stored,
            "stage": "content_generation",
            "plan_approved": True,
            "current_post_id": post_id,
            "is_regeneration": True,
            "regen_attempt_number": attempts,
            "feedback_strength": classify_feedback_strength(text),
            "human_feedback_text": text,
            "force_variation": True,
            "random_seed": hashlib.sha256(f"{post_id}|{attempts}|{time.time()}".encode()).hexdigest(),
            "previous_variants": fb_dict["previous_variants"].get(pid_norm, [])
        }

        # Invoke regeneration
        try:
            result_state = await system_agents.ainvoke(state_input)
            new_plan = result_state.get("campaign_plan", plan)
            # Extract regenerated content
            new_node = new_plan[parts[0]][f"{parts[1]}_{parts[2]}"][parts[3]]
            content = new_node.get("content","")
            # Similarity check
            if not similarity_ok(content, fb_dict["previous_variants"].get(pid_norm, [])):
                # force one more regeneration with boosted temp
                state_input["force_variation"] = True
                state_input["random_seed"] = hashlib.sha256((state_input["random_seed"]+"retry").encode()).hexdigest()
                result_state = await system_agents.ainvoke(state_input)
                new_plan = result_state.get("campaign_plan", new_plan)
                new_node = new_plan[parts[0]][f"{parts[1]}_{parts[2]}"][parts[3]]
                content = new_node.get("content","")
            # Update full plan and previous_variants
            plan = new_plan
            fb_dict["previous_variants"].setdefault(pid_norm, []).append({"content":content})
            details[post_id] = {"success": True, "attempts": attempts}
        except Exception as e:
            details[post_id] = {"success": False, "message": str(e)}

    # Upload Excel only
    excel_url = generate_and_upload_combined_excel_to_s3(plan, campaign_full, bucket=S3_BUCKET, version=max(fb_dict["current_attempts"].values()))
    
    # Persist updated plan & feedback in DB
    update_agentic_campaign_planner(
        username=username,
        campaign_name=campaign_name,
        approved_plan=json.dumps({"campaign_plan":plan}, ensure_ascii=False),
        feedback_response=json.dumps(fb_dict, ensure_ascii=False),
        regeneration_count=max(fb_dict["current_attempts"].values())
    )

    return {
        "campaign_name": campaign_full,
        "success": True,
        "campaign_plan": plan,
        "details": details,
        "excel_s3_url": excel_url
    }

