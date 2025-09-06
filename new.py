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

graph = StateGraph(State)

# ------------------------ SYSTEM AGENT NODES ------------------------
graph.add_node("orchestrator_agent", orchestrator_agent)
graph.add_node("system_agent_orchestrator", system_agent_orchestrator)
graph.add_node("web_search_agent", web_search_tool)              # unchanged
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
    if state.get("is_regeneration", False) or state.get("current_post_id"):
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

graph.add_edge("plan_generator", "__end__")
graph.add_edge("system_agent_orchestrator", "web_search_agent")
graph.add_edge("web_search_agent", "prompt_optimization")
graph.add_edge("prompt_optimization", "text_generator")
graph.add_edge("text_generator", "content_reviewer")
graph.add_edge("content_reviewer", "content_validator")
graph.add_edge("content_validator", "social_media_agents_supervisor")

# ------------------------ SOCIAL MEDIA ROUTER ------------------------
def social_media_router(state: State) -> str:
    post_id = state.get("current_post_id")
    if post_id:
        platform = post_id.split("_")[0].lower()
        if platform in PLATFORM_AGENT_MAP:
            return f"create_{platform}_post"
    # fallback to first platform
    first = state.get("platforms", ["instagram"])[0]
    return f"create_{first}_post"

graph.add_conditional_edges(
    "social_media_agents_supervisor",
    social_media_router,
    [
        "create_instagram_post", "create_facebook_post", "create_x_post",
        "create_whatsapp_post", "create_email_post", "create_sms_post"
    ]
)

# End after a single post in regeneration
for node in [
    "create_instagram_post", "create_facebook_post", "create_x_post",
    "create_whatsapp_post", "create_email_post", "create_sms_post"
]:
    graph.add_edge(node, "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()





from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime
import json, copy, hashlib
from src.agent.graph import system_agents
from .db_utils import (
    get_user_by_username, get_user_campaigns,
    get_agentic_planner_record, update_agentic_campaign_planner
)
from .excel_generator import generate_and_upload_combined_excel_to_s3
from src.models import MultiFeedbackRequest
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Regenerate specific posts based on user feedback,
    calling the platform agent directly for the given post_id.
    """
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(404, "User not found")

    if not get_user_campaigns(username):
        raise HTTPException(404, "No campaigns for user")

    feedbacks = feedback_request.feedbacks or []
    if not feedbacks:
        raise HTTPException(400, "Feedback list cannot be empty")

    # Deduplicate by post_id
    seen, dedup = set(), []
    for fb in feedbacks:
        pid = fb.post_id.strip()
        if pid and pid.lower() not in seen:
            seen.add(pid.lower())
            dedup.append(fb)

    planner = get_agentic_planner_record(username, campaign_name)
    if not planner:
        raise HTTPException(404, "Planner record not found")

    raw = planner.get("approve_response") or planner.get("plan_response")
    stored = json.loads(raw) if isinstance(raw, str) else raw
    full_plan = copy.deepcopy(stored["campaign_plan"])

    # Load feedback state
    fb_state = planner.get("feedback_response") or {}
    fb_state = json.loads(fb_state) if isinstance(fb_state, str) else fb_state
    attempts = fb_state.get("current_regen_attempts", {})
    prev_vars = fb_state.get("previous_variants", {})

    details = {}
    processed = []

    # Import platform agents
    from src.agent.campaign_agent.social_media_agents import (
        create_instagram_post, create_facebook_post, create_x_post,
        create_whatsapp_post, create_email_post, create_sms_post
    )
    AGENTS = {
        "instagram": create_instagram_post,
        "facebook": create_facebook_post,
        "x": create_x_post,
        "whatsapp": create_whatsapp_post,
        "email": create_email_post,
        "sms": create_sms_post
    }

    def strength(txt):
        low = (txt or "").lower()
        if any(w in low for w in ["rewrite", "start over", "completely change"]): return "strong"
        if any(w in low for w in ["improve", "enhance", "better"]): return "medium"
        return "light"

    def temp(at, strg):
        base = {"light":0.8, "medium":0.85, "strong":0.9}[strg]
        return base if at==1 else min(base+0.1,0.95)

    def seed(pid, at, txt):
        s = f"{pid}|{at}|{(txt or '')[:50]}|{datetime.utcnow().isoformat()}"
        return hashlib.sha256(s.encode()).hexdigest()

    # Process each feedback
    for fb in dedup:
        pid = fb.post_id.strip()
        at = attempts.get(pid.lower(), 0) + 1
        attempts[pid.lower()] = at
        strg = strength(fb.feedback_text)
        tp = temp(at, strg)
        sd = seed(pid, at, fb.feedback_text)

        parts = pid.split("_")
        if len(parts) < 3:
            details[pid] = {"success": False, "message": "Invalid post_id"}
            continue

        plat = parts[0].lower()
        week = f"{parts[1]}_{parts[2]}"
        day  = "_".join(parts[3:]) if len(parts)>3 else "Day_1"

        agent_fn = AGENTS.get(plat)
        if not agent_fn:
            details[pid] = {"success": False, "message": f"No agent for {plat}"}
            continue

        # Build regeneration state
        state = {
            "platform": plat,
            "current_week": week,
            "current_day": int(day.split("_")[-1]),
            "regen_attempt_number": at,
            "human_feedback_text": fb.feedback_text,
            "feedback_strength": strg,
            "temperature_override": tp,
            "random_seed": sd,
            "previous_variants": prev_vars.get(pid.lower(), []),
            "is_regeneration": True,
            **stored  # includes campaign_objective, target_audience, etc.
        }

        # Call platform agent directly
        result = agent_fn(state)
        new_content = result.get("content") or ""
        # Update plan
        full_plan[plat][week][day]["content"] = new_content
        full_plan[plat][week][day]["human_feedback"] = fb.feedback_text
        full_plan[plat][week][day]["regeneration_count"] = at

        # Save variant
        prev_vars.setdefault(pid.lower(), []).append({
            "content": new_content, "attempt": at, "temperature": tp,
            "timestamp": datetime.utcnow().isoformat()
        })

        details[pid] = {"success": True, "message": "Regenerated"}
        processed.append(pid)

    # Upload new Excel
    excel_url = generate_and_upload_combined_excel_to_s3(
        full_plan,
        f"{username}/{campaign_name}",
        bucket=S3_BUCKET,
        version=max(attempts.values())
    )

    # Persist state
    fb_state["current_regen_attempts"] = attempts
    fb_state["previous_variants"] = prev_vars
    update_agentic_campaign_planner(
        username=username,
        campaign_name=campaign_name,
        feedback_response=json.dumps(fb_state),
        regeneration_count=max(attempts.values())
    )

    return {
        "campaign_name": f"{username}/{campaign_name}",
        "success": True,
        "message": f"Processed {len(processed)} posts",
        "excel_s3_url": excel_url,
        "details": details
    }
