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
from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from botocore.exceptions import ClientError

from src.database.operations import (
    get_user_by_username,
    get_user_campaigns,
    update_agentic_campaign_planner
)
from src.storage.s3 import s3_client, store_json_to_s3
from src.agent.graph import system_agents
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
    - Skips vector DB (Pinecone) during feedback runs
    - Produces versioned approved_plan_v{n}.json and versioned final excel
    - Persists feedback.json with approved_plan_versions history
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing multi-feedback for {campaign_full_name}")

        # Validate user & campaign
        user_data = get_user_by_username(username)
        if not user_
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

            # Validate post exists inside campaign_plan
            found = False
            for platform, platform_data in (campaign_plan or {}).items():
                if isinstance(platform_data, dict):
                    for week_key, week_data in platform_data.items():
                        if isinstance(week_data, dict):
                            for day_key in week_data.keys():
                                candidate = f"{platform}_{week_key}_{day_key}"
                                if candidate == post_id or day_key == post_id:
                                    found = True
                                    break
                            if found:
                                break
                    if found:
                        break

            if not found:
                post_result.update({
                    "message": f"Post ID '{post_id}' not found in campaign plan.",
                    "success": False
                })
                aggregated_results["results"][post_id] = post_result
                continue

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

            # Invoke the compiled graph for this post only
            try:
                final_state = await system_agents.ainvoke(state_input)
                final_state_dict = dict(final_state)
                logger.info(f"Regenerated content for {post_id}, version={version_number}")
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
                "campaign_plan": final_state_dict.get("campaign_plan", campaign_plan),
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
                # important: include the human feedback so excel generator can populate the column
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

            # Update DB with feedback_response and regenration_count
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



def generate_and_upload_combined_excel_to_s3(
    campaign_plan: Dict[str, Any],
    campaign_name: str,
    bucket: str,
    plan_ Dict[str, Any],
    version: int = None
) -> str:
    """
    Generate a combined Excel file with sheets for each platform and upload to S3.
    Populates 'Human Feedback' and 'Regen Attempts' columns from plan_data.
    Handles versioning in the file name if version is provided.
    """
    writer = pd.ExcelWriter(io.BytesIO(), engine='openpyxl')
    platforms = list(campaign_plan.keys())

    for platform in platforms:
        if should_skip_platform(platform, campaign_plan[platform]):
            continue

        data = []
        for week_key, week_data in campaign_plan[platform].items():
            for day_key, day_info in week_data.items():
                post_id = f"{platform}_{week_key}_{day_key}"
                task = clean_task_content(day_info.get('task', ''), platform, day_key)
                content = day_info.get('content', '')
                clean_content, images = extract_content_and_images(content)
                image_str = '; '.join(images) if images else ''

                # Get human feedback and regen count from plan_data
                human_feedback = plan_data.get('human_feedback_map', {}).get(post_id, '')
                regen_attempts = plan_data.get('regen_attempts_map', {}).get(post_id, 0)

                data.append({
                    'Week': week_key.capitalize(),
                    'Day': day_key,
                    'Task': task,
                    'Content': clean_content,
                    'Images': image_str,
                    'Human Feedback': human_feedback,  # Populated here
                    'Regen Attempts': regen_attempts   # New column
                })

        if 
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name=platform.capitalize(), index=False)
            worksheet = writer.sheets[platform.capitalize()]
            enable_wrap_text(worksheet)

    # Save to BytesIO and upload to S3
    writer.close()
    excel_buffer = writer.book.save(io.BytesIO())
    excel_buffer.seek(0)

    # Versioned key
    version_suffix = f"_v{version}" if version else ""
    s3_key = f"campaigns/{campaign_name.replace('/', '_')}/final_combined{version_suffix}.xlsx"

    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=excel_buffer,
        ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    # Return presigned URL or just the key (adjust as needed)
    return f"https://{bucket}.s3.amazonaws.com/{s3_key}"
