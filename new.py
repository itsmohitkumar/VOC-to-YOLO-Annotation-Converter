# src/agent/graph.py
from typing import Dict, Any
from langgraph.graph import StateGraph
from src.models import State

from src.campaign_agent.system_agents import (
    orchestrator_agent,
    system_agent_orchestrator,
    prompt_optimization,
    text_generator,
    image_generator,
    content_reviewer,
    plan_generator,
    content_validator,
    web_search_tool,
    PLATFORM_AGENT_MAP  # Assuming this is defined in system_agents.py
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
graph.add_node("image_generator", image_generator)
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
        print("🔄 Regeneration mode detected: Routing directly to social media agents supervisor")
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
graph.add_edge("text_generator", "image_generator")
graph.add_edge("image_generator", "content_reviewer")
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

# In regeneration mode, end after platform agent (skipping formatter/feedback)
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()



# src/api/feedback.py
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
import inspect
import logging

from src.database.operations import (
    get_user_by_username,
    get_user_campaigns,
    update_agentic_campaign_planner
)
from src.storage.s3 import s3_client, store_json_to_s3
from src.agent.graph import system_agents
# Import platform agents directly so feedback regen can call them and skip the graph/vector DB
from src.agent.campaign_agent.social_media_agents import (
    create_instagram_post,
    create_facebook_post,
    create_x_post,
    create_whatsapp_post,
    create_email_post,
    create_sms_post
)
from utils.excel_generator import generate_and_upload_combined_excel_to_s3
from utils.logger import logger
from utils.env_vars import S3_BUCKET

router = APIRouter()

# Request models
class PostFeedback(BaseModel):
    post_id: str
    feedback_text: str

class MultiFeedbackRequest(BaseModel):
    feedbacks: List[PostFeedback]


def _default_post_result(post_id: str) -> Dict[str, Any]:
    return {
        "post_id": post_id,
        "success": False,
        "message": "Not processed",
        "campaign_plan": {},
        "regeneration_attempts": 0,
        "version": None,
        "excel_s3_url": ""
    }


# map platform name -> function
PLATFORM_AGENT_FN_MAP = {
    "instagram": create_instagram_post,
    "facebook": create_facebook_post,
    "x": create_x_post,
    "twitter": create_x_post,  # legacy alias
    "whatsapp": create_whatsapp_post,
    "email": create_email_post,
    "sms": create_sms_post
}


def find_post_in_plan(campaign_plan: Dict[str, Any], post_id: str) -> Optional[Tuple[str, str, str]]:
    """
    Find the platform, week_key, day_key for a given post_id.
    Expected post_id formats:
        - "<platform>_<week_key>_<day_key>"  e.g. "sms_week_1_Day_1"
        - or day_key itself, but prefer the above.
    Returns tuple (platform, week_key, day_key) or None if not found.
    """
    if not campaign_plan:
        return None
    for platform, platform_data in campaign_plan.items():
        if not isinstance(platform_data, dict):
            continue
        for week_key, week_data in platform_data.items():
            if not isinstance(week_data, dict):
                continue
            for day_key in week_data.keys():
                candidate = f"{platform}_{week_key}_{day_key}"
                if candidate == post_id or day_key == post_id:
                    return (platform, week_key, day_key)
    return None


@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Batch feedback endpoint:
    - Accepts list of feedback items: [{post_id, feedback_text}, ...]
    - Regenerates only those posts
    - Skips vector DB (Pinecone) during feedback runs by directly calling platform agents
      when possible.
    - Produces versioned approved_plan_v{n}.json and versioned final excel
    - Persists feedback.json with approved_plan_versions history
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing multi-feedback for {campaign_full_name}")

        # Validate user & campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")

        user_campaigns = get_user_campaigns(username)
        if not user_campaigns:
            raise HTTPException(status_code=404, detail=f"No campaigns found for user '{username}'")

        campaign_match = next((c for c in user_campaigns if c['campaign_name'].lower() == campaign_name.lower()), None)
        if not campaign_match:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")

        # Load approved_plan (preferred) or fallback to plan.json
        campaign_plan = None
        try:
            plan_obj = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/approved_plan.json"
            )
            campaign_plan = json.loads(plan_obj["Body"].read().decode("utf-8")).get("campaign_plan")
            logger.info(f"Loaded approved_plan.json for {campaign_full_name}")
        except s3_client.exceptions.NoSuchKey:
            try:
                plan_obj = s3_client.get_object(
                    Bucket=S3_BUCKET,
                    Key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/plan.json"
                )
                campaign_plan = json.loads(plan_obj["Body"].read().decode("utf-8")).get("campaign_plan")
                logger.info(f"Loaded plan.json for {campaign_full_name}")
            except s3_client.exceptions.NoSuchKey:
                raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")

        if not campaign_plan:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")

        # Load or initialize feedback.json
        try:
            fb_obj = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/feedback.json"
            )
            feedback_dict = json.loads(fb_obj["Body"].read().decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            feedback_dict = {
                "campaign_name": campaign_full_name,
                "feedback_history": [],
                "current_regen_attempts": {},
                "max_regen_attempts": 3,
                "approved_plan_versions": []
            }

        # Load plan state metadata if exists
        try:
            state_obj = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/plan.json"
            )
            state_dict = json.loads(state_obj["Body"].read().decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            state_dict = {
                "campaign_name": campaign_full_name,
                "campaign_plan": campaign_plan,
                "current_regen_attempts": feedback_dict.get("current_regen_attempts", {}),
                "max_regen_attempts": feedback_dict.get("max_regen_attempts", 3),
                "is_regen_required": True
            }

        aggregated_results: Dict[str, Any] = {"campaign_name": campaign_full_name, "results": {}}
        human_feedback_map: Dict[str, str] = {}  # collects feedback per post to pass into plan_data -> excel

        # Sequentially process each feedback to avoid race conditions on S3/DB writes
        for fb in feedback_request.feedbacks:
            post_id = fb.post_id
            fb_text = fb.feedback_text or ""
            post_result = _default_post_result(post_id)

            # Find the platform/week/day for this post
            found_location = find_post_in_plan(campaign_plan, post_id)
            if not found_location:
                post_result.update({
                    "message": f"Post ID '{post_id}' not found in campaign plan.",
                    "success": False
                })
                aggregated_results["results"][post_id] = post_result
                continue

            platform, week_key, day_key = found_location

            # Regen attempt bookkeeping
            current_regen_attempts = feedback_dict.get("current_regen_attempts", {})
            current_attempts = current_regen_attempts.get(post_id, 0)
            max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)

            if current_attempts >= max_regen_attempts:
                history_entry = {
                    "post_id": post_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "feedback_text": fb_text,
                    "regen_attempt_number": current_attempts + 1,
                    "note": "Max attempts reached"
                }
                feedback_dict.setdefault("feedback_history", []).append(history_entry)
                post_result.update({
                    "message": f"Maximum regeneration attempts ({max_regen_attempts}) reached for '{post_id}'",
                    "success": False,
                    "regeneration_attempts": current_attempts
                })
                aggregated_results["results"][post_id] = post_result
                continue

            # Append feedback history & increment attempts
            feedback_entry = {
                "post_id": post_id,
                "timestamp": datetime.utcnow().isoformat(),
                "feedback_text": fb_text,
                "regen_attempt_number": current_attempts + 1
            }
            feedback_dict.setdefault("feedback_history", []).append(feedback_entry)
            current_regen_attempts[post_id] = current_attempts + 1
            feedback_dict["current_regen_attempts"] = current_regen_attempts

            # Map feedback for excel insertion
            human_feedback_map[post_id] = fb_text

            # Build state input for agents for this single-post regeneration
            version_number = current_regen_attempts.get(post_id, 1)
            state_input = {
                **state_dict,
                **feedback_dict,
                "stage": "content_generation",
                "plan_approved": True,
                "base_plan_dict": campaign_plan,
                "current_post_id": post_id,
                "regen_attempt_number": version_number,
                "human_feedback_text": fb_text,
                "is_regeneration": True
            }

            # -------------------------
            # DIRECT PLATFORM AGENT RUN
            # -------------------------
            final_state_dict: Dict[str, Any] = {}
            try:
                agent_fn = PLATFORM_AGENT_FN_MAP.get(platform)
                if agent_fn:
                    logger.info(f"Calling platform agent directly for platform='{platform}', post_id='{post_id}' (skipping graph).")
                    # sanitize state to reduce chance of vector DB usage inside agent
                    sanitized_state = dict(state_input)
                    sanitized_state["search_results"] = ""
                    sanitized_state["optimized_prompts"] = {}
                    sanitized_state["generated_images"] = []

                    # call sync or async agent safely
                    if inspect.iscoroutinefunction(agent_fn):
                        result = await agent_fn(sanitized_state)
                    else:
                        result = agent_fn(sanitized_state)

                    result = result or {}
                    # Determine the key (e.g., 'sms_post', 'instagram_post', etc.)
                    result_key = f"{platform}_post"
                    post_obj = result.get(result_key, {}) if isinstance(result, dict) else {}

                    # Extract generated fields
                    generated_content = ""
                    generated_task = ""
                    if isinstance(post_obj, dict):
                        generated_content = post_obj.get("content", "") or post_obj.get("body", "") or ""
                        generated_task = post_obj.get("task_description", "") or post_obj.get("task", "") or ""

                    # Update only the specific day entry in campaign_plan
                    try:
                        day_entry = campaign_plan.setdefault(platform, {}).setdefault(week_key, {}).setdefault(day_key, {})
                        # Update fields carefully
                        if generated_task:
                            day_entry["task"] = generated_task
                        if generated_content:
                            day_entry["content"] = generated_content
                        # ensure human feedback and regen count are recorded
                        day_entry["human_feedback"] = fb_text
                        day_entry["regeneration_count"] = day_entry.get("regeneration_count", 0) + 1
                        day_entry["status"] = "Generated"
                        # preserve image_path_s3 if present; agent may not return images
                        if "image_path_s3" not in day_entry:
                            day_entry["image_path_s3"] = day_entry.get("image_path_s3", [])
                    except Exception as ex:
                        logger.error(f"Failed to merge agent result into campaign_plan for {post_id}: {ex}")

                    # Build final_state_dict to include updated campaign_plan and agent messages
                    final_state_dict = {
                        "campaign_plan": campaign_plan,
                        "current_step": result.get("current_step", f"create_{platform}_post"),
                        "messages": result.get("messages", [f"Regenerated {platform} post {post_id}"]),
                        "generated_images": result.get("generated_images", []),
                        "image_generation_status": result.get("image_generation_status", "skipped")
                    }
                    logger.info(f"Regenerated content for {post_id} via direct agent call, version={version_number}")
                else:
                    # fallback: call the compiled graph (this may trigger other nodes)
                    logger.info(f"No direct platform agent found for '{platform}', falling back to graph invocation for {post_id}")
                    # ensure we explicitly set keys to avoid vector lookups where possible
                    state_input["search_results"] = ""
                    state_input["optimized_prompts"] = {}
                    final_state = await system_agents.ainvoke(state_input)
                    final_state_dict = dict(final_state)
                    # Merge returned campaign_plan if present
                    if final_state_dict.get("campaign_plan"):
                        campaign_plan = final_state_dict.get("campaign_plan")
                    logger.info(f"Regenerated content for {post_id} via graph invocation, version={version_number}")

            except Exception as e:
                logger.error(f"Error regenerating {post_id}: {e}")
                post_result.update({
                    "message": f"Error during regeneration: {str(e)}",
                    "success": False
                })
                aggregated_results["results"][post_id] = post_result
                continue

            # Build approved_plan_data for this version and attach human_feedback_map
            approved_plan_data = {
                "campaign_name": campaign_full_name,
                # use updated campaign_plan
                "campaign_plan": campaign_plan,
                "current_step": final_state_dict.get("current_step", "completed"),
                "messages": final_state_dict.get("messages", []),
                "stage": "content_generation",
                "plan_approved": True,
                "campaign_objective": state_dict.get("campaign_objective", ""),
                "campaign_description": state_dict.get("campaign_description", ""),
                "start_date": state_dict.get("start_date", ""),
                "end_date": state_dict.get("end_date", ""),
                "target_audience": state_dict.get("target_audience", ""),
                "target_audience_info": state_dict.get("target_audience_info", []),
                "platforms": state_dict.get("platforms", []),
                "generated_images": final_state_dict.get("generated_images", []),
                "image_generation_status": final_state_dict.get("image_generation_status", "skipped"),
                "generated_at": datetime.utcnow().isoformat(),
                # include the human feedback so excel generator can populate the column
                "human_feedback_map": human_feedback_map.copy()
            }

            # Persist versioned approved_plan and latest
            versioned_key = f"campaigns/{username}/{campaign_name}/campaign_planner/response/approved_plan_v{version_number}.json"
            latest_key = f"campaigns/{username}/{campaign_name}/campaign_planner/response/approved_plan.json"
            try:
                store_json_to_s3(bucket=S3_BUCKET, key=versioned_key, data=approved_plan_data)
                store_json_to_s3(bucket=S3_BUCKET, key=latest_key, data=approved_plan_data)
            except Exception as e:
                logger.error(f"Failed storing approved_plan for {post_id}: {e}")

            # Generate & upload versioned final excel (pass plan_data so excel picks up human_feedback_map)
            excel_s3_url = ""
            try:
                excel_s3_url = generate_and_upload_combined_excel_to_s3(
                    campaign_plan=approved_plan_data["campaign_plan"],
                    campaign_name=campaign_full_name,
                    bucket=S3_BUCKET,
                    plan_data=approved_plan_data,
                    version=version_number
                )
                # write excel url back into plan and persist again
                approved_plan_data["excel_s3_url"] = excel_s3_url
                store_json_to_s3(bucket=S3_BUCKET, key=versioned_key, data=approved_plan_data)
                store_json_to_s3(bucket=S3_BUCKET, key=latest_key, data=approved_plan_data)
            except Exception as e:
                logger.error(f"Failed generate/upload excel for {post_id} v{version_number}: {e}")

            # Append to feedback_dict approved_plan_versions history
            approved_history_entry = {
                "version": version_number,
                "approved_plan_key": versioned_key,
                "excel_s3_url": excel_s3_url,
                "post_id": post_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            feedback_dict.setdefault("approved_plan_versions", []).append(approved_history_entry)

            # Update DB with feedback_response and regeneration_count
            try:
                update_agentic_campaign_planner(
                    username=username,
                    campaign_name=campaign_name,
                    feedback_response=json.dumps({
                        "feedback": feedback_dict,
                        "final_state": final_state_dict
                    }, ensure_ascii=False),
                    regenration_count=sum(feedback_dict.get("current_regen_attempts", {}).values())
                )
            except Exception as e:
                logger.error(f"Failed DB update for {campaign_full_name}: {e}")

            # Build post_result to return
            final_regen_attempts = feedback_dict.get("current_regen_attempts", {}).get(post_id, 0)
            post_result.update({
                "success": True,
                "message": "Feedback processed and post regenerated",
                "campaign_plan": approved_plan_data.get("campaign_plan", {}),
                "regeneration_attempts": final_regen_attempts,
                "version": version_number,
                "excel_s3_url": excel_s3_url
            })
            aggregated_results["results"][post_id] = post_result

        # After processing all feedbacks, persist feedback.json
        try:
            store_json_to_s3(bucket=S3_BUCKET, key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/feedback.json", data=feedback_dict)
            logger.info(f"Persisted feedback.json for {campaign_full_name}")
        except Exception as e:
            logger.error(f"Failed to persist feedback.json: {e}")

        return aggregated_results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in submit_feedback: {e}")
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

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import json
from src.llm.bedrock import call_bedrock_for_text

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """
    Supervisor agent that coordinates social media content generation.
    """
    return {
        "messages": ["Social media agents supervisor initialized"],
        "current_step": "social_media_agents_supervisor"
    }

def create_instagram_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates professional Instagram posts using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"
    
    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )
    
    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.8
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"
    
    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."
    
    content_prompt = INSTAGRAM_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=1000,
            temperature=0.8
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"
    
    instagram_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "instagram_post": instagram_post,
        "messages": [f"Generated Instagram post for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_instagram_post"
    }

def create_facebook_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates strategic Facebook posts using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"

    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )

    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.7
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"

    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."

    content_prompt = FACEBOOK_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=1000,
            temperature=0.8
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"

    facebook_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "facebook_post": facebook_post,
        "messages": [f"Generated Facebook post for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_facebook_post"
    }

def create_x_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates strategic X (Twitter) posts using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"

    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )

    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.7
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"

    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."

    content_prompt = X_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=500,
            temperature=0.8
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"

    x_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "x_post": x_post,
        "messages": [f"Generated X post for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_x_post"
    }

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates strategic WhatsApp messages using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"

    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )

    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.7
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"

    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."

    content_prompt = WHATSAPP_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=800,
            temperature=0.8
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"

    whatsapp_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "whatsapp_post": whatsapp_post,
        "messages": [f"Generated WhatsApp message for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_whatsapp_post"
    }

def create_email_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates strategic email communications using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "valued subscriber")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"

    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )

    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.7
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"

    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."

    content_prompt = EMAIL_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=1200,
            temperature=0.7
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"

    email_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "email_post": email_post,
        "messages": [f"Generated email for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_email_post"
    }

def create_sms_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates SMS posts using AWS Bedrock.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"

    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        phase=phase,
        day_context=day_context
    )

    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.7
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"

    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."

    content_prompt = SMS_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=300,
            temperature=0.8
        )
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"

    sms_post = {
        "task_description": task_description,
        "content": actual_content
    }

    return {
        "sms_post": sms_post,
        "messages": [f"Generated SMS for day {current_day} created successfully using AWS Bedrock"],
        "current_step": "create_sms_post"
    }


#excel_generator.py:
 
import pandas as pd
from typing import Dict, Any
import boto3
from datetime import datetime
import io
import re
from utils.env_vars import *
from openpyxl.styles import Alignment
 
# Initialize S3 client using environment variables
s3_client = boto3.client('s3', region_name=AWS_REGION)
 
# Use the environment variable for S3 bucket name
S3_BUCKET = AWS_AGENTIC_BUCKET
 
# =====================HELPER FUNCTIONS====================
def is_error_content(content: str) -> bool:
    """Check if content contains error messages."""
    error_patterns = [
        r'error',
        r'throttlingexception',
        r'no agent found'
    ]
    for pattern in error_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False
 
 
def should_skip_platform(platform: str, weeks: Dict[str, Any]) -> bool:
    """Check if a platform should be skipped (e.g., all tasks are 'No agent found')."""
    for week_key, days in weeks.items():
        for day_key, day_data in days.items():
            if not is_error_content(day_data.get('task', '')):
                return False
    return True
 
 
def clean_task_content(content: str, platform: str, day_key: str) -> str:
    """Clean and format task content."""
    # Remove redundant quotes
    content = content.strip('"').strip("'")
    # Capitalize first letter
    if content:
        content = content[0].upper() + content[1:]
    return content
 
 
def extract_content_and_images(content: str) -> tuple:
    """
    Extract clean content and image paths from mixed content.
    """
    if not content:
        return "", []
   
    # Patterns to identify image descriptions
    image_patterns = [
        r'\*\*Image:\*\*[^\n]*',
        r'\*\*Visuals:\*\*[^\n]*',
        r'\(Image:[^)]*\)',
        r'\(Visuals:[^)]*\)',
        r'Image:[^\n]*',
        r'Visuals:[^\n]*'
    ]
   
    image_paths = []
    clean_content = content
   
    # Extract image descriptions
    for pattern in image_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            # Clean up the image description
            image_desc = re.sub(r'\*\*|Image:|Visuals:|\(|\)', '', match).strip()
            if image_desc:
                image_paths.append(image_desc)
            # Remove from content
            clean_content = re.sub(re.escape(match), '', clean_content)
   
    # Clean up the content
    clean_content = re.sub(r'\n\s*\n', '\n\n', clean_content)  # Remove extra newlines
    clean_content = clean_content.strip()
   
    return clean_content, image_paths
 
def enable_wrap_text(ws):
   """Enable wrap text for cells with multi-line content."""
   for row in ws.iter_rows():
       for cell in row:
           if isinstance(cell.value, str) and "\n" in cell.value:
               cell.alignment = Alignment(wrap_text=True)
 
def auto_adjust_column_widths(ws):
   """Auto-adjust column widths based on cell content length."""
   for col in ws.columns:
       max_length = 0
       col_letter = col[0].column_letter
       for cell in col:
           try:
               if cell.value:
                   length = len(str(cell.value))
                   if length > max_length:
                       max_length = length
           except Exception:
               pass
       ws.column_dimensions[col_letter].width = min(max_length + 2, 60)  # cap width
 
# =====================FILE MANAGEMENT FUNCTIONS====================
def upload_excel_to_s3(excel_content: bytes, s3_key: str, bucket: str) -> str:
    """
    Upload Excel file content to S3.
    """
    try:
        s3_client = boto3.client('s3')
       
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=excel_content,
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
       
        # Return S3 URL
        return f"s3://{bucket}/{s3_key}"
       
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return ""
 
# =====================EXCEL GENERATION FUNCTIONS====================
def generate_campaign_excel(campaign_plan: Dict[str, Any], campaign_name: str, stage: str = "plan") -> bytes:
    """
    Generate Excel file from campaign plan data.
    """
    # Create Excel writer with multiple sheets
    output = io.BytesIO()
   
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
       
        if stage == "draft" or stage == "plan":
            # Generate plan overview Excel for draft stage
            generate_plan_overview_excel(campaign_plan, writer)
        else:
            # Generate full content Excel for final stage
            generate_content_excel(campaign_plan, writer)
   
    output.seek(0)
    return output.read()
 
def generate_plan_overview_excel(campaign_plan: Dict[str, Any], writer) -> None:
    """Generate Excel sheets for plan overview stage (DRAFT)."""
 
    # Create overview data for DRAFT stage - only basic columns
    overview_data = []
 
    for platform, weeks in campaign_plan.items():
        # Skip platforms with no valid agents
        if should_skip_platform(platform, weeks):
            continue
 
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                task_content = clean_task_content(day_data.get('task', ''), platform, day_key)
 
                # Skip entries with errors or no valid content
                if not task_content or is_error_content(task_content):
                    continue
 
                overview_data.append({
                    'Platform': platform.title(),
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': task_content,
                    'Status': 'Pending Approval'
                })
 
    # Create DataFrame and save to Excel with "Campaign Plan" sheet name
    if overview_data:
        df_overview = pd.DataFrame(overview_data)
        df_overview.to_excel(writer, sheet_name='Campaign Plan', index=False)
 
def generate_content_excel(campaign_plan: Dict[str, Any], writer) -> None:
    for platform, weeks in campaign_plan.items():
        content_data = []
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                raw_content = day_data.get('content', '')
                clean_content, image_paths = extract_content_and_images(raw_content)
                stored_image_paths = day_data.get('image_path_s3', [])
                if isinstance(stored_image_paths, list):
                    all_image_paths = image_paths + stored_image_paths
                else:
                    all_image_paths = image_paths + [stored_image_paths] if stored_image_paths else image_paths
                content_data.append({
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': day_data.get('task', ''),
                    'Content': clean_content,
                    'Image Paths': '\n'.join(all_image_paths) if all_image_paths else '',
                    'Human Feedback': day_data.get('human_feedback', ''),   # ✅ simplified
                    'Regeneration Count': day_data.get('regeneration_count', 0),
                    'Status': 'Generated' if day_data.get('content') else 'Pending'
                })
        if content_data:
            df_content = pd.DataFrame(content_data)
            sheet_name = platform.title()
            df_content.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            enable_wrap_text(ws)
            auto_adjust_column_widths(ws)
                       
def generate_approved_plan_overview_excel(campaign_plan: Dict[str, Any], writer) -> None:
    overview_data = []
    for platform, weeks in campaign_plan.items():
        if should_skip_platform(platform, weeks):
            continue
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                task_content = clean_task_content(day_data.get('task', ''), platform, day_key)
                if not task_content or is_error_content(task_content):
                    continue
                overview_data.append({
                    'Platform': platform.title(),
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': task_content,
                    'Status': 'Approved'
                })
    if overview_data:
        df_overview = pd.DataFrame(overview_data)
        sheet_name = 'Approved Campaign Plan'
        df_overview.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        enable_wrap_text(ws)
        auto_adjust_column_widths(ws)
       
def generate_full_campaign_plan_excel(campaign_plan: Dict[str, Any], writer) -> None:
    """Generate full approved campaign plan with Task, Content, Images, Feedback, Regeneration Count, and Status."""
    full_data = []
    for platform, weeks in campaign_plan.items():
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                task_content = clean_task_content(day_data.get('task', ''), platform, day_key)
                if not task_content or is_error_content(task_content):
                    continue
                clean_content, image_paths = extract_content_and_images(day_data.get('content', ''))
                stored_image_paths = day_data.get('image_path_s3', [])
                if isinstance(stored_image_paths, list):
                    all_image_paths = image_paths + stored_image_paths
                else:
                    all_image_paths = image_paths + [stored_image_paths] if stored_image_paths else image_paths
                full_data.append({
                    'Platform': platform.title(),
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': task_content,
                    'Content': clean_content,
                    'Image Paths': '\n'.join(all_image_paths) if all_image_paths else '',
                    'Human Feedback': day_data.get('human_feedback', ''),   # ✅ simplified
                    'Regeneration Count': day_data.get('regeneration_count', 0),
                    'Status': day_data.get('status', 'Approved')
                })
    if full_data:
        df_full = pd.DataFrame(full_data)
        sheet_name = 'Full Campaign Plan'
        df_full.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        enable_wrap_text(ws)
        auto_adjust_column_widths(ws)
       
def generate_combined_excel(campaign_plan: Dict[str, Any], campaign_name: str, plan_data: Dict[str, Any] = None) -> bytes:
    """
    Create a combined workbook: Approved Overview + Full Campaign Plan + Content sheets.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        generate_approved_plan_overview_excel(campaign_plan, writer)
        generate_full_campaign_plan_excel(campaign_plan, writer)
        generate_content_excel(campaign_plan, writer)
    output.seek(0)
    return output.read()
 
# =====================PUBLIC API FUNCTIONS====================
def generate_and_upload_excel_to_s3(
    campaign_plan: Dict[str, Any],
    campaign_name: str,
    stage: str,
    bucket: str
) -> str:
    """
    Generate Excel file and upload directly to S3.
    """
    excel_content = generate_campaign_excel(campaign_plan, campaign_name, stage)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    s3_key = f"campaigns/{campaign_name}/excel/{stage}_{timestamp}.xlsx"
    s3_url = upload_excel_to_s3(excel_content, s3_key, bucket)
    return s3_url
 
def generate_and_upload_combined_excel_to_s3(
    campaign_plan: Dict[str, Any],
    campaign_name: str,
    bucket: str,
    plan_data: Dict[str, Any] = None,
    version: int = 1
    ) -> str:
    """
    Generate combined excel and upload with a versioned filename:
    <username>_<campaign>_final_v{version}.xlsx
    campaign_name should be the 'username/campaign_name' format to keep S3 path consistent.
    """
    # create excel bytes
    excel_content = generate_combined_excel(campaign_plan, campaign_name, plan_data)
    # sanitize name for filename; keep folder path intact in s3_key
    clean_campaign_path = campaign_name.replace("/", "_")
    filename = f"{clean_campaign_path}_final_v{version}.xlsx"
    s3_key = f"campaigns/{campaign_name}/campaign_planner/excel/{filename}"
    s3_url = upload_excel_to_s3(excel_content, s3_key, bucket)
    return s3_url
    
          
##System_agents.py:
 
from typing import Dict, Any
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
    Main orchestrator agent that coordinates the entire workflow.
    Determines if we're in plan generation or content generation stage.
    """
    # Check if plan is already approved and we need to generate content
    if state.get("plan_approved") and state.get("stage") == "content_generation":
        return {
            "messages": ["Orchestrator: Starting content generation phase"],
            "current_step": "orchestrator_agent",
            "stage": "content_generation"
        }
    else:
        # Default to plan generation stage
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
    collection_name = state.get("collection_name", "default_collection")
   
    # Base prompt elements
    base_prompt_elements = {
        "objective": campaign_objective,
        "description": campaign_description,
        "audience": target_audience,
        "theme": state.get("campaign_theme"),
        "location": state.get("target_location", "Global")
    }
   
    # Enhanced prompt elements using vector database and web search context
    enhanced_prompt_elements = base_prompt_elements.copy()
   
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
           
            # Create context-enhanced prompts
            context_keywords = []
           
            # Analyze context insights for relevant keywords and themes
            for insight in context_insights[:5]:  # Use top 5 insights
                # Extract potential keywords (simplified approach)
                words = insight.lower().split()
                # Look for campaign-relevant terms
                relevant_terms = [word for word in words if len(word) > 4 and
                                any(keyword in word for keyword in ['campaign', 'brand', 'message', 'content', 'audience', 'strategy'])]
                context_keywords.extend(relevant_terms[:2])  # Limit keywords per insight
           
            # Remove duplicates and limit total keywords
            context_keywords = list(set(context_keywords))[:10]
           
            # Enhance prompt elements with context
            if context_keywords:
                enhanced_prompt_elements["context_keywords"] = context_keywords
           
            if web_search_results:
                enhanced_prompt_elements["web_search_results"] = web_search_results
 
            if context_sources:
                enhanced_prompt_elements["reference_sources"] = list(set(context_sources))[:3]  # Top 3 unique sources
           
            # Create context-aware prompt guidance
            context_guidance = f"Incorporate insights from {len(context_insights)} relevant context sources and web search results"
            if context_keywords:
                context_guidance += f", focusing on themes related to: {', '.join(context_keywords[:5])}"
           
            enhanced_prompt_elements["context_guidance"] = context_guidance
            enhanced_prompt_elements["context_insights"] = context_insights[:3]  # Store top 3 insights
           
            messages = [
                "Prompt optimization completed with vector database and web search context integration",
                f"Enhanced prompts with {len(context_insights)} context insights from {len(set(context_sources))} sources and web search results",
                f"Extracted {len(context_keywords)} relevant keywords for content focus"
            ]
            context_enhanced = True
        else:
            # Fallback when no context is available
            enhanced_prompt_elements["context_guidance"] = "Using campaign parameters only - no relevant context found in vector database"
            if web_search_results:
                 enhanced_prompt_elements["web_search_results"] = web_search_results
            messages = [
                "Prompt optimization completed using campaign parameters and web search results only",
                "No relevant context found in vector database - using standard optimization approach with web search"
            ]
            context_enhanced = False
           
    except Exception as e:
        # Handle any errors with hybrid search
        enhanced_prompt_elements["context_guidance"] = "Using campaign parameters only - error accessing vector database"
        messages = [
            "Prompt optimization completed using campaign parameters only",
            f"Error accessing vector database: {str(e)} - using standard optimization approach"
        ]
        context_enhanced = False
   
    return {
        "messages": messages,
        "current_step": "prompt_optimization",
        "optimized_prompts": enhanced_prompt_elements,
        "context_enhanced": context_enhanced
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
 
def image_generator(state: State) -> Dict[str, Any]:
    """
    Image generation agent that creates image content.
    """
    return {
        "messages": ["Image generation completed"],
        "current_step": "image_generator"
    }
 
def content_reviewer(state: State) -> Dict[str, Any]:
    """
    Content review agent that reviews generated content.
    """
    return {
        "messages": ["Content review completed"],
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
   
    campaign_plan = {}
    for platform in platforms:
        campaign_plan[platform] = {}
        for week_key, week_data in base_plan.items():
            week_num = week_key.lower()
            campaign_plan[platform][week_num] = {}
            for day_index, day_info in enumerate(week_data):
                day_key = f"Day_{day_index + 1}"
                agent_f = PLATFORM_AGENT_MAP.get(platform)
                if agent_f:
                    agent_state = state.copy()
                    agent_state["current_day"] = day_index + 1
                    agent_state["total_days"] = len(week_data)
                    try:
                        result = agent_f(agent_state)
                        post = result.get(f"{platform}_post")
                        # For the plan, we just need the task description
                        task_description = post.get('task_description') or f"AI-generated content for {platform}"
                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description
                        }
                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"Error generating task: {str(e)}"
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No agent found for {platform}"
                    }
   
    return {
        "messages": ["Campaign plan outline generated - awaiting approval"],
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
   
    # Create full content structure using AI agents
    campaign_plan = {}
   
    for platform in platforms:
        campaign_plan[platform] = {}
       
        for week_key, week_data in base_plan.items():
            week_num = week_key.lower()
            campaign_plan[platform][week_num] = {}
           
            for day_index, day_info in enumerate(week_data):
                day_key = f"Day_{day_index + 1}"
               
                # Get the appropriate AI agent for the platform
                agent_f = PLATFORM_AGENT_MAP.get(platform)
                if agent_f:
                    # Create a new state for the agent call
                    agent_state = state.copy()
                    agent_state["current_day"] = day_index + 1
                    agent_state["total_days"] = len(week_data)
                   
                    try:
                        # Call the AI agent to generate the content
                        result = agent_f(agent_state)
                        # Extract the AI-generated post from the result
                        post = result.get(f"{platform}_post")
                       
                        # Extract the actual content from the post object
                        if isinstance(post, dict):
                            # Extract content and task description from the post
                            content_text = post.get("content", "")
                            task_description = post.get("task_description", f"AI-generated {platform} content for day {day_index + 1}")
                        else:
                            content_text = str(post) if post else ""
                            task_description = f"AI-generated {platform} content for day {day_index + 1}"
                       
                        # Generate S3 image paths (simulated)
                        image_paths = []
                        if platform != "sms":  # SMS typically doesn't have images
                            campaign_name = state.get("campaign_name", "campaign").replace("/", "_")
                            image_paths = [f"s3://campaign-assets/{campaign_name}/{platform}/day_{day_index + 1}_image_{i+1}.jpg" for i in range(2)]
                       
                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description,
                            "content": content_text,  # AI-generated content as string
                            "image_path_s3": image_paths,
                            "human_feedback": ""
                        }
                    except Exception as e:
                        # Fallback if AI generation fails
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"AI generation error for {platform}",
                            "content": f"Error generating content: {str(e)}",
                            "image_path_s3": [],
                            "human_feedback": ""
                        }
                else:
                    # Fallback if no agent is found
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No AI agent found for {platform}",
                        "content": f"Platform {platform} not supported",
                        "image_path_s3": [],
                        "human_feedback": ""
                    }
   
    return {
        "messages": [f"AI-powered content generated for '{campaign_theme or 'campaign'}' using AWS Bedrock"],
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
