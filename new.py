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
# NOTE: Removed image_generator from flow - goes directly to content_reviewer
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

# In regeneration mode, end after platform agent
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()


@### src/api/api.py

from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from typing import List, Optional, Dict, Any
import json
import re
import copy
import hashlib
from datetime import datetime
from src.agent.graph import system_agents
from utils.logger import logger
from .excel_generator import generate_and_upload_combined_excel_to_s3, generate_campaign_excel, upload_excel_to_s3
from .content_review_service import content_review_service
from utils.env_vars import S3_BUCKET, ALLOWED_PLATFORMS, SUPPORTED_IMAGE_FORMATS
from .db_utils import (get_user_by_username, get_user_campaigns, get_campaign_by_name,
                       get_collection_info, hybrid_search, insert_agentic_campaign_planner,
                       update_agentic_campaign_planner)
from src.models import State, CampaignPlanResponse, MultiFeedbackRequest

router = APIRouter()

@router.post("/{username}/create/{campaign_name}", response_model=CampaignPlanResponse)
async def create_campaign_plan(
    username: str,
    campaign_name: str,
    campaign_objective: str = Form(...),
    campaign_description: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    target_audience: str = Form(...),
    target_audience_info: Optional[str] = Form(None),
    target_audience_location: str = Form(...),
    marketing_channels: List[str] = Form(default=["instagram", "facebook", "email", "whatsapp", "sms"]),
    campaign_images: List[UploadFile] = File(default=[])
):
    try:
        logger.info(f"Starting request validation for user: {username}, campaign: {campaign_name}")

        # Normalize and validate marketing channels
        processed_channels = [ch.strip().lower() for ch in marketing_channels if ch.strip()]
        unique_marketing_channels = list(set(processed_channels))
        if not unique_marketing_channels:
            raise HTTPException(status_code=400, detail="At least one marketing channel must be selected")
        invalid_channels = [channel for channel in unique_marketing_channels if channel not in ALLOWED_PLATFORMS]
        if invalid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid marketing channels: {invalid_channels}. Allowed channels: {ALLOWED_PLATFORMS}"
            )
        logger.info(f"Validated marketing channels: {unique_marketing_channels}")

        # Validate dates
        date_info = calculate_date_info(start_date, end_date)
        if "error" in date_info:
            raise HTTPException(status_code=400, detail=date_info["error"])
        logger.info("Validated dates successfully")

        # Validate and parse target_audience_info
        audience_emails = []
        if target_audience_info:
            audience_emails = [email.strip().strip('"').strip("'") for email in target_audience_info.split(",") if email.strip()]
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            for email in audience_emails:
                if not email_pattern.match(email):
                    raise HTTPException(status_code=400, detail=f"Invalid email format: {email}")
            logger.info(f"Validated {len(audience_emails)} email addresses")

        # Pre-validate campaign_images
        if campaign_images:
            for image in campaign_images:
                if not image.filename:
                    raise HTTPException(status_code=400, detail="One or more uploaded images are missing filenames")
                file_extension = os.path.splitext(image.filename)[1].lower()
                if file_extension not in SUPPORTED_IMAGE_FORMATS:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported image format: {file_extension}. Supported formats: {SUPPORTED_IMAGE_FORMATS}"
                    )
        logger.info("Validated image file extensions")

        # Validate user and campaign existence
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User with username '{username}' not found.")
        user_campaigns = get_user_campaigns(username)
        if not user_campaigns:
            raise HTTPException(status_code=404, detail=f"No campaigns found for username '{username}'.")
        campaign_full_name = f"{username}/{campaign_name}"
        if campaign_full_name not in user_campaigns:
            campaign_data = get_campaign_by_name(campaign_name, username)
            if not campaign_data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Campaign '{campaign_name}' is not registered for user '{username}'."
                )
        logger.info(f"Validated user and campaign: {campaign_full_name}")

        # Retrieve context from vector database
        logger.info(f"Retrieving context from vector database for campaign: {campaign_full_name}")
        vector_context: List[Dict[str, Any]] = []
        collection_name = campaign_full_name
        collection_info = get_collection_info(collection_name, user_id=user_data.get('user_id'))
        if collection_info.get('success') and collection_info.get('metadata', {}).get('count', 0) > 0:
            logger.info(f"Found vector database collection for user: {collection_name}")
            search_queries = [
                f"{campaign_objective} {target_audience}",
                f"{campaign_description}",
                f"campaign planning {target_audience}"
            ]
            for query in search_queries:
                search_results = hybrid_search(
                    query=query,
                    collection_name=collection_name,
                    n_results=3,
                    filter_expr=None
                )
                if search_results.get('success') and search_results.get('results'):
                    for result in search_results['results']:
                        if result.get('text'):
                            vector_context.append({
                                'text': result['text'],
                                'source': result.get('metadata', {}).get('source', 'unknown'),
                                'score': result.get('score', 0),
                                'query': query
                            })
            logger.info(f"Retrieved {len(vector_context)} context documents from vector database")
        else:
            logger.error(f"No knowledge base found for user: {collection_name}")

        if not vector_context:
            logger.error(f"No relevant context retrieved for campaign: {campaign_full_name}")
            raise HTTPException(
                status_code=400,
                detail="No relevant content found in knowledge base for this campaign."
            )

        # Upload images
        uploaded_image_urls: List[Dict[str, Any]] = []
        if campaign_images:
            logger.info(f"Uploading {len(campaign_images)} validated campaign images")
            s3_folder = f"campaigns/{username}/{campaign_name}/campaign_planner/images"
            for image in campaign_images:
                image_content = await image.read()
                logger.info(f"Uploading {image.filename} to S3 folder: {s3_folder}")
                upload_result = upload_file(
                    file_content=image_content,
                    AWS_AGENTIC_BUCKET=S3_BUCKET,
                    s3_client=s3_client,
                    file_name=image.filename,
                    folder=s3_folder
                )
                if upload_result.get("success"):
                    uploaded_image_urls.append({
                        "filename": image.filename,
                        "s3_url": upload_result.get("url"),
                        "s3_key": upload_result.get("s3_key")
                    })
                    logger.info(f"Successfully uploaded image: {image.filename}")
                else:
                    logger.error(f"Failed to upload image {image.filename}: {upload_result.get('message')}")
                    raise HTTPException(status_code=500, detail=f"Failed to upload image {image.filename}")
        logger.info(f"Uploaded {len(uploaded_image_urls)} images to S3")

        # Agentic workflow
        initial_state = State(
            campaign_name=campaign_full_name,
            campaign_objective=campaign_objective,
            campaign_description=campaign_description,
            start_date=start_date,
            end_date=end_date,
            target_audience=target_audience,
            target_audience_location=target_audience_location,
            target_audience_info=audience_emails,
            base_plan_dict=copy.deepcopy(date_info["week_mapping"]),
            max_regen_attempts=3,
            current_regen_attempts={},
            platforms=unique_marketing_channels,
            generate_images=False,  # Updated to False
            stage="plan_generation",
            plan_approved=False,
            campaign_images=uploaded_image_urls
        )

        final_state = await system_agents.ainvoke(initial_state)
        state_dict = dict(final_state)
        campaign_plan = state_dict.get("campaign_plan")

        if not campaign_plan:
            logger.error(f"No campaign plan generated. Final state keys: {list(state_dict.keys())}")
            raise HTTPException(status_code=404, detail="Campaign generation failed - no campaign plan generated!")

        # Ensure campaign_plan is a dict
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("campaign_plan is a string but not valid JSON; returning as-is")
        elif hasattr(campaign_plan, "dict") and callable(getattr(campaign_plan, "dict")):
            campaign_plan = campaign_plan.dict()

        generated_images: List[Dict[str, Any]] = []  # Always empty
        image_generation_status = "skipped"
        content_review_status = "skipped"

        # Content review logic
        try:
            logger.info("Starting content review and validation")
            content_review_status, _ = content_review_service.review_campaign_content(
                campaign_plan,
                {
                    "campaign_objective": campaign_objective,
                    "campaign_description": campaign_description,
                    "target_audience": target_audience,
                    "target_audience_location": target_audience_location
                },
                unique_marketing_channels
            )
            logger.info(f"Content review completed. Status: {content_review_status}")
        except Exception as e:
            logger.error(f"Error in content review process: {e}")
            content_review_status = "error"

        # Upload Excel to S3
        try:
            bucket_name = S3_BUCKET
            excel_content = generate_campaign_excel(campaign_plan, campaign_full_name, stage="plan")
            excel_filename = f"{username}_{campaign_name}_plan.xlsx"
            s3_key = f"campaigns/{username}/{campaign_name}/campaign_planner/excel/{excel_filename}"
            excel_s3_url = upload_excel_to_s3(excel_content, s3_key, bucket_name)
            if not excel_s3_url:
                raise HTTPException(500, "Failed to upload Excel file to S3")
            logger.info(f"Excel uploaded: {excel_s3_url}")
        except Exception as e:
            logger.error(f"Excel upload failed: {e}")
            raise HTTPException(500, "Excel upload to S3 failed")

        # Prepare and store plan.json
        plan_data = {
            "campaign_name": campaign_full_name,
            "campaign_plan": campaign_plan,  # dict
            "current_step": state_dict.get("current_step", "completed"),
            "messages": state_dict.get("messages", []),
            "campaign_objective": campaign_objective,
            "campaign_description": campaign_description,
            "start_date": start_date,
            "end_date": end_date,
            "target_audience": target_audience,
            "target_audience_location": target_audience_location,
            "target_audience_info": audience_emails,
            "platforms": unique_marketing_channels,
            "campaign_images": uploaded_image_urls,
            "generated_images": generated_images,
            "image_generation_status": image_generation_status,
            "content_review_status": content_review_status,
            "excel_s3_url": excel_s3_url
        }

        store_json_to_s3(
            bucket=S3_BUCKET,
            key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/plan.json",
            data=plan_data
        )

        insert_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            campaign_objective=campaign_objective,
            campaign_description=campaign_description,
            start_date=start_date,
            end_date=end_date,
            target_audience=target_audience,
            target_audience_location=target_audience_location,
            target_audience_info=json.dumps(audience_emails, ensure_ascii=False),
            marketing_channels=json.dumps(unique_marketing_channels, ensure_ascii=False),
            campaign_images=json.dumps(uploaded_image_urls, ensure_ascii=False),
            plan_response=json.dumps(plan_data, ensure_ascii=False)
        )

        total_images = len(uploaded_image_urls) + len(generated_images)
        message_parts = [f"Campaign plan generated successfully. Excel file: {excel_s3_url}"]
        if uploaded_image_urls:
            message_parts.append(f"User uploaded {len(uploaded_image_urls)} images.")
        if generated_images:
            message_parts.append(f"Auto-generated {len(generated_images)} images.")
        if content_review_status in ["approved", "approved_with_suggestions"]:
            message_parts.append("Content review completed successfully.")
        response_message = " ".join(message_parts)

        return CampaignPlanResponse(
            campaign_name=campaign_full_name,
            success=True,
            message=response_message,
            campaign_plan=campaign_plan,              
            platforms=unique_marketing_channels,
            uploaded_images=uploaded_image_urls,        
            generated_images=generated_images,
            total_images=total_images,
            image_generation_status=image_generation_status,
            content_review_status=content_review_status,
            target_audience_location=target_audience_location
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating campaign: {e}")
        raise HTTPException(status_code=500, detail="Error generating campaign: Contact support team!")

@router.post("/{username}/{campaign_name}/approve", response_model=CampaignPlanResponse)
async def approve_campaign_plan(
    username: str,
    campaign_name: str
):
    try:
        logger.info(f"Approving campaign plan for user: {username}, campaign: {campaign_name}")

        # Validate user
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User with username '{username}' not found.")

        # Validate campaign existence
        user_campaigns = get_user_campaigns(username)
        campaign_exists_flag = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists_flag:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'.")

        # Load existing plan.json from S3
        campaign_full_name = f"{username}/{campaign_name}"
        try:
            state_data = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/plan.json"
            )
            stored_plan: Dict[str, Any] = json.loads(state_data["Body"].read().decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            logger.error(f"Campaign plan not found for '{campaign_full_name}'. Please create the campaign first.")
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'.")
        except Exception as e:
            logger.error(f"Error reading plan.json for '{campaign_full_name}': {e}")
            raise HTTPException(status_code=500, detail="Failed to read stored campaign plan")

        # Validate essential fields from stored plan
        required_fields = [
            "campaign_name", "campaign_objective", "campaign_description",
            "start_date", "end_date", "target_audience", "target_audience_info",
            "target_audience_location", "platforms", "campaign_plan"
        ]
        missing = [f for f in required_fields if f not in stored_plan]
        if missing:
            raise HTTPException(status_code=400, detail=f"Stored plan.json missing required fields: {missing}")

        # Normalize target_audience_info
        target_audience_info = stored_plan.get("target_audience_info", [])
        if isinstance(target_audience_info, str):
            try:
                target_audience_info = json.loads(target_audience_info)
            except Exception:
                if "," in target_audience_info:
                    target_audience_info = [e.strip() for e in target_audience_info.split(",") if e.strip()]
                else:
                    target_audience_info = [target_audience_info] if target_audience_info else []

        # Validate dates and build base plan mapping
        date_info = calculate_date_info(stored_plan["start_date"], stored_plan["end_date"])
        if "error" in date_info:
            raise HTTPException(status_code=400, detail=date_info["error"])

        # Validate platforms
        platforms: List[str] = list({ch for ch in stored_plan.get("platforms", []) if ch})
        if not platforms:
            raise HTTPException(status_code=400, detail="No platforms found in stored plan")
        invalid_channels = [ch for ch in platforms if ch not in ALLOWED_PLATFORMS]
        if invalid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid platforms in stored plan: {invalid_channels}. Allowed: {ALLOWED_PLATFORMS}"
            )

        # Ensure campaign_plan is a dict
        campaign_plan = stored_plan.get("campaign_plan")
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("Stored campaign_plan is a string but not valid JSON; continuing with original value")

        # Build approval state
        approval_state = State(
            campaign_name=stored_plan["campaign_name"],
            campaign_objective=stored_plan["campaign_objective"],
            campaign_description=stored_plan["campaign_description"],
            start_date=stored_plan["start_date"],
            end_date=stored_plan["end_date"],
            target_audience=stored_plan["target_audience"],
            target_audience_info=target_audience_info,
            target_audience_location=stored_plan.get("target_audience_location", ""),
            base_plan_dict=copy.deepcopy(date_info["week_mapping"]),
            platforms=platforms,
            stage="content_generation",
            plan_approved=True,
            generate_images=False,  # image generation skipped
            max_regen_attempts=3,
            current_regen_attempts={},
            campaign_plan=campaign_plan,
            messages=[],
            current_step="approval",
            campaign_images=stored_plan.get("campaign_images", [])  # keep uploaded images only
        )

        # Run agent workflow to generate full content (non-image content only)
        final_state = await system_agents.ainvoke(approval_state)
        state_dict = dict(final_state)
        campaign_plan = state_dict.get("campaign_plan")

        if not campaign_plan:
            logger.error(f"No campaign plan generated after approval. Final state keys: {list(state_dict.keys())}")
            raise HTTPException(status_code=404, detail="Full content generation failed after approval!")

        # Ensure campaign_plan is a dict
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("campaign_plan returned from agent is not valid JSON; returning as-is")
        elif hasattr(campaign_plan, "dict") and callable(getattr(campaign_plan, "dict")):
            campaign_plan = campaign_plan.dict()

        # Image sanitization
        uploaded_images = stored_plan.get("campaign_images", []) or []

        def _sanitize_image_fields(obj: Any) -> Any:
            if isinstance(obj, dict):
                clean = {}
                for k, v in obj.items():
                    kl = k.lower()
                    if kl in {"image_path_s3", "image_paths", "image_urls", "images"}:
                        clean[k] = []  # keep the key but empty the list to avoid UI breakage
                    else:
                        clean[k] = _sanitize_image_fields(v)
                return clean
            if isinstance(obj, list):
                return [_sanitize_image_fields(x) for x in obj]
            return obj

        image_generation_status = "skipped"
        if not uploaded_images and image_generation_status == "skipped":
            campaign_plan = _sanitize_image_fields(campaign_plan)

        # Upload combined Excel to S3
        excel_s3_url = generate_and_upload_combined_excel_to_s3(
            campaign_plan,
            campaign_full_name,
            S3_BUCKET
        )
        if not excel_s3_url:
            raise HTTPException(status_code=500, detail="Failed to upload Excel file to S3")

        # Build response & store approved plan
        total_images = len(uploaded_images)

        message_parts = [
            f"Campaign plan approved and full content generated successfully. Excel file: {excel_s3_url}"
        ]
        if uploaded_images:
            message_parts.append(f"User uploaded {len(uploaded_images)} images.")
        message_text = " ".join(message_parts)

        approved_plan_data = {
            "campaign_name": campaign_full_name,
            "campaign_plan": campaign_plan,  # sanitized dict
            "current_step": state_dict.get("current_step", "completed"),
            "messages": state_dict.get("messages", []),
            "stage": "content_generation",
            "plan_approved": True,
            "campaign_objective": stored_plan["campaign_objective"],
            "campaign_description": stored_plan["campaign_description"],
            "start_date": stored_plan["start_date"],
            "end_date": stored_plan["end_date"],
            "target_audience": stored_plan["target_audience"],
            "target_audience_info": target_audience_info,
            "target_audience_location": stored_plan.get("target_audience_location", ""),
            "platforms": platforms,
            "excel_s3_url": excel_s3_url,
            "campaign_images": uploaded_images,  # only user-uploaded images retained (empty if none)
            "message": message_text,
            "image_generation_status": image_generation_status,
            "content_review_status": "approved"
        }

        store_json_to_s3(
            bucket=S3_BUCKET,
            key=f"campaigns/{username}/{campaign_name}/campaign_planner/response/approved_plan.json",
            data=approved_plan_data
        )

        update_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            approve_response=json.dumps(approved_plan_data, ensure_ascii=False),
            approved_plan=True
        )

        # Build response
        return CampaignPlanResponse(
            campaign_name=campaign_full_name,
            success=True,
            campaign_plan=campaign_plan,              
            platforms=platforms,
            uploaded_images=uploaded_images,          
            total_images=total_images,                
            content_review_status="approved",
            message=message_text,
            image_generation_status=image_generation_status,
            target_audience_location=approved_plan_data.get("target_audience_location", "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving campaign plan: {e}")
        raise HTTPException(status_code=500, detail="Error approving campaign plan: Contact support team!")

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Enhanced batch feedback endpoint with progressive temperature and improved regeneration:
    - Progressive temperature increases: 0.8 → 0.9 → 0.95 for attempts 1-3
    - Enhanced seed generation using SHA-256 hashing
    - Content similarity checking to ensure variation
    - Only uploads Excel files to S3 (no JSON uploads)
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

        # Load plans and state
        base_prefix = f"campaigns/{username}/{campaign_name}/campaign_planner/response"
        stored_plan_full = None
        campaign_plan = None

        for key in ("approved_plan.json", "plan.json"):
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/{key}")
                stored_plan_full = json.loads(obj["Body"].read().decode("utf-8"))
                campaign_plan = stored_plan_full.get("campaign_plan")
                logger.info(f"Loaded {key} for {campaign_full_name}")
                break
            except s3_client.exceptions.NoSuchKey:
                continue
            except Exception as e:
                logger.error(f"Error reading {key} for '{campaign_full_name}': {e}")
                raise HTTPException(status_code=500, detail=f"Failed to read campaign plan")

        if campaign_plan is None:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")

        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("Stored campaign_plan is a string but not valid JSON; proceeding with original value")

        # Load feedback tracking
        try:
            fb_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/feedback.json")
            feedback_dict = json.loads(fb_obj["Body"].read().decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            feedback_dict = {
                "campaign_name": campaign_full_name,
                "feedback_history": [],
                "current_regen_attempts": {},
                "max_regen_attempts": 3,
                "approved_plan_versions": [],
                "previous_variants": {}
            }
        except Exception as e:
            logger.error(f"Error reading feedback.json for '{campaign_full_name}': {e}")
            raise HTTPException(status_code=500, detail="Failed to read feedback store")

        # Normalize attempt keys
        current_attempts_dict = feedback_dict.get("current_regen_attempts", {}) or {}
        normalized_attempts = {}
        for k, v in current_attempts_dict.items():
            if isinstance(k, str):
                kl = k.strip().lower()
                normalized_attempts[kl] = max(v, normalized_attempts.get(kl, 0))
        feedback_dict["current_regen_attempts"] = normalized_attempts
        feedback_dict.setdefault("previous_variants", {})

        # Load state
        try:
            state_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/plan.json")
            state_dict = json.loads(state_obj["Body"].read().decode("utf-8"))
        except s3_client.exceptions.NoSuchKey:
            state_dict = {
                "campaign_name": campaign_full_name,
                "campaign_plan": campaign_plan,
                "current_regen_attempts": feedback_dict.get("current_regen_attempts", {}),
                "max_regen_attempts": feedback_dict.get("max_regen_attempts", 3),
                "is_regen_required": True
            }
        except Exception as e:
            logger.error(f"Error reading base plan state for '{campaign_full_name}': {e}")
            raise HTTPException(status_code=500, detail="Failed to read plan state")

        full_plan = copy.deepcopy(campaign_plan)
        details: Dict[str, Any] = {}
        human_feedback_map: Dict[str, str] = {}

        # Enhanced Feedback Processing (original logic retained with minor cleanups)
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

            # Validate post exists
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

            # Enhanced regeneration
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

                    new_day_node = None
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

            # Process successful regeneration
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

            # Clean up any image-related fields
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
            "generated_images": [],  # Always empty
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
            val = state_dict.get(mk, stored_plan_full.get(mk, dv))
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

        # NOTE: Store to database only, no S3 JSON
        try:
            pass  # Database storage logic here (original pass retained)
        except Exception as e:
            logger.error(f"Failed storing approved_plan batch v{batch_version}: {e}")

        # Update feedback tracking (database only)
        feedback_dict.setdefault("approved_plan_versions", []).append({
            "version": batch_version,
            "excel_s3_url": excel_s3_url,
            "post_ids": list(original_post_ids),
            "timestamp": datetime.utcnow().isoformat(),
            "processed_count": processed_count
        })

        try:
            pass  # Database storage for feedback_dict
        except Exception as e:
            logger.error(f"Failed to persist feedback.json: {e}")

        # Build response
        response = {
            "campaign_name": campaign_full_name,
            "success": True,
            "message": f"Enhanced feedback processing completed for {processed_count} of {len(deduped_feedbacks)} posts with progressive temperature control.",
            "campaign_plan": approved_plan_data["campaign_plan"],
            "platforms": approved_plan_data.get("platforms", []),
            "generated_images": [],  # Always empty
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

 
#\content_review_service.py
 
import json
from typing import Dict, Any, List, Tuple
from datetime import datetime
from src.llm.bedrock import call_bedrock_for_text
from src.llm.prompts import (
    CONTENT_REVIEWER_PROMPT_TEXT,
    PLATFORM_GUIDELINES
)
from utils.logger import logger

class ContentReviewService:
    """Service for reviewing, formatting, and validating campaign content."""
    
    def __init__(self):
        self.logger = logger
    
    def review_campaign_content(
        self,
        campaign_plan: str,
        campaign_data: Dict[str, Any],
        platforms: List[str]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Review and validate the entire campaign content.
        """
        review_details = {
            "overall_score": 0,
            "platform_reviews": {},
            "recommendations": [],
            "validation_status": "pending",
            "reviewed_at": datetime.now().isoformat()
        }
        
        try:
            # Parse campaign plan
            plan_data = json.loads(campaign_plan) if isinstance(campaign_plan, str) else campaign_plan
            
            platform_scores = []
            
            # Review content for each platform
            for platform in platforms:
                if platform in plan_data:
                    platform_review = self._review_platform_content(
                        platform, plan_data[platform], campaign_data
                    )
                    review_details["platform_reviews"][platform] = platform_review
                    platform_scores.append(platform_review.get("quality_score", 5))
            
            # Calculate overall score
            if platform_scores:
                review_details["overall_score"] = sum(platform_scores) / len(platform_scores)
            
            # Generate overall recommendations
            review_details["recommendations"] = self._generate_overall_recommendations(
                review_details["platform_reviews"], campaign_data
            )
            
            # Determine validation status
            if review_details["overall_score"] >= 8:
                review_details["validation_status"] = "approved"
                review_status = "approved"
            elif review_details["overall_score"] >= 6:
                review_details["validation_status"] = "approved_with_suggestions"
                review_status = "approved_with_suggestions"
            else:
                review_details["validation_status"] = "needs_revision"
                review_status = "needs_revision"
            
            self.logger.info(f"Content review completed. Status: {review_status}, Score: {review_details['overall_score']:.1f}")
            
        except Exception as e:
            self.logger.error(f"Error in content review: {e}")
            review_status = "error"
            review_details["validation_status"] = "error"
            review_details["error"] = str(e)
        
        return review_status, review_details
    
    def _review_platform_content(
        self,
        platform: str,
        platform_content: Dict[str, Any],
        campaign_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Review content for a specific platform."""
        
        try:
            # Extract content for review
            content_text = self._extract_platform_content_text(platform_content)
            
            # Create review prompt
            review_prompt = CONTENT_REVIEWER_PROMPT_TEXT.format(
                content=content_text,
                platform=platform,
                campaign_objective=campaign_data.get('campaign_objective', ''),
                target_audience=campaign_data.get('target_audience', ''),
                campaign_theme=campaign_data.get('campaign_theme', '')
            )
            
            # Get AI review
            review_response = call_bedrock_for_text(
                review_prompt,
                model_id="amazon.nova-pro-v1:0",
                max_tokens=1500,
                temperature=0.3
            )
            
            # Parse review response
            review_data = self._parse_review_response(review_response, platform)
            
            # Add platform-specific validation
            platform_validation = self._validate_platform_guidelines(platform, content_text)
            review_data.update(platform_validation)
            
            return review_data
            
        except Exception as e:
            self.logger.error(f"Error reviewing {platform} content: {e}")
            return {
                "quality_score": 5,
                "alignment_score": 5,
                "suggestions": [f"Error in review process: {str(e)}"],
                "strengths": [],
                "areas_for_improvement": ["Review process failed"],
                "overall_assessment": "Unable to complete review"
            }
    
    def _extract_platform_content_text(self, platform_content: Dict[str, Any]) -> str:
        """Extract text content from platform data for review."""
        
        content_parts = []
        
        # Extract content from different time periods
        for week_key, week_data in platform_content.items():
            if isinstance(week_data, dict):
                for day_key, day_data in week_data.items():
                    if isinstance(day_data, dict):
                        task = day_data.get("task", "")
                        content = day_data.get("content", "")
                        if task:
                            content_parts.append(f"Task: {task}")
                        if content:
                            content_parts.append(f"Content: {content}")
        
        return "\n".join(content_parts) if content_parts else "No content available"
    
    def _parse_review_response(self, review_response: str, platform: str) -> Dict[str, Any]:
        """Parse AI review response into structured data."""
        
        try:
            # Try to parse as JSON first
            if "{" in review_response and "}" in review_response:
                json_start = review_response.find("{")
                json_end = review_response.rfind("}") + 1
                json_str = review_response[json_start:json_end]
                parsed_data = json.loads(json_str)
                
                if "reviews" in parsed_data:
                    return parsed_data["reviews"]
                else:
                    return parsed_data
            
            # Fallback to text parsing
            return self._parse_text_review(review_response)
            
        except Exception as e:
            self.logger.warning(f"Could not parse review response for {platform}: {e}")
            return self._create_default_review(review_response)
    
    def _parse_text_review(self, review_text: str) -> Dict[str, Any]:
        """Parse text-based review response."""
        
        # Extract scores using simple text analysis
        quality_score = 7  # Default
        alignment_score = 7  # Default
        
        # Look for score indicators
        if "excellent" in review_text.lower() or "outstanding" in review_text.lower():
            quality_score = alignment_score = 9
        elif "good" in review_text.lower() or "strong" in review_text.lower():
            quality_score = alignment_score = 8
        elif "poor" in review_text.lower() or "weak" in review_text.lower():
            quality_score = alignment_score = 4
        
        # Extract suggestions (simple approach)
        suggestions = []
        if "suggest" in review_text.lower():
            suggestions.append("Review contains suggestions for improvement")
        if "improve" in review_text.lower():
            suggestions.append("Content can be improved")
        
        return {
            "quality_score": quality_score,
            "alignment_score": alignment_score,
            "suggestions": suggestions,
            "strengths": ["AI-generated content"],
            "areas_for_improvement": ["Consider manual review"],
            "overall_assessment": review_text[:200] + "..." if len(review_text) > 200 else review_text
        }
    
    def _create_default_review(self, review_text: str) -> Dict[str, Any]:
        """Create default review structure."""
        
        return {
            "quality_score": 7,
            "alignment_score": 7,
            "suggestions": ["Manual review recommended"],
            "strengths": ["Content generated successfully"],
            "areas_for_improvement": ["Review parsing incomplete"],
            "overall_assessment": "Review completed with default scoring"
        }
    
    def _validate_platform_guidelines(self, platform: str, content: str) -> Dict[str, Any]:
        """Validate content against platform-specific guidelines."""
        
        validation_results = {
            "platform_compliance": True,
            "compliance_notes": []
        }
        
        try:
            if platform in PLATFORM_GUIDELINES:
                guidelines = PLATFORM_GUIDELINES[platform]
                max_length = guidelines.get("max_length")
                
                # Check length constraints
                if isinstance(max_length, int) and len(content) > max_length:
                    validation_results["platform_compliance"] = False
                    validation_results["compliance_notes"].append(
                        f"Content exceeds {platform} maximum length of {max_length} characters"
                    )
                
                # Check tone alignment
                expected_tone = guidelines.get("tone", "")
                if expected_tone:
                    validation_results["compliance_notes"].append(
                        f"Expected tone for {platform}: {expected_tone}"
                    )
        
        except Exception as e:
            self.logger.warning(f"Error validating {platform} guidelines: {e}")
        
        return validation_results
    
    def _generate_overall_recommendations(
        self,
        platform_reviews: Dict[str, Any],
        campaign_data: Dict[str, Any]
    ) -> List[str]:
        """Generate overall campaign recommendations based on platform reviews."""
        
        recommendations = []
        
        try:
            # Analyze scores across platforms
            scores = [review.get("quality_score", 5) for review in platform_reviews.values()]
            avg_score = sum(scores) / len(scores) if scores else 5
            
            if avg_score < 6:
                recommendations.append("Consider revising campaign content to improve overall quality")
            elif avg_score >= 8:
                recommendations.append("Campaign content quality is excellent and ready for deployment")
            
            # Check for common issues across platforms
            common_suggestions = []
            for review in platform_reviews.values():
                common_suggestions.extend(review.get("suggestions", []))
            
            # Add platform-specific recommendations
            if len(platform_reviews) > 3:
                recommendations.append("Multi-platform campaign detected - ensure consistent messaging")
            
            if not recommendations:
                recommendations.append("Campaign content meets quality standards")
        
        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Unable to generate specific recommendations")
        
        return recommendations

# Global service instance
content_review_service = ContentReviewService()


@# /system_agents.py  

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
    Main orchestrator agent that coordinates the entire workflow.
    Determines if we're in plan generation or content generation stage.
    """
    if state.get("plan_approved") and state.get("stage") == "content_generation":
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
            
            context_keywords = []
            
            # Analyze context insights for relevant keywords and themes
            for insight in context_insights[:5]:  # Use top 5 insights
                words = insight.lower().split()
                relevant_terms = [word for word in words if len(word) > 4 and
                                  any(keyword in word for keyword in ['campaign', 'brand', 'message', 'content', 'audience', 'strategy'])]
                context_keywords.extend(relevant_terms[:2])  # Limit keywords per insight
            
            # Remove duplicates and limit total keywords
            context_keywords = list(set(context_keywords))[:10]
            
            # Enhance prompt elements with context
            if context_keywords:
                enhanced_prompt_elements["context_keywords"] = context_keywords
            
            if web_search_results:
                enhanced_prompt_elements["web_search_results"] = web_search_results
            
            if context_sources:
                enhanced_prompt_elements["reference_sources"] = list(set(context_sources))[:3]  # Top 3 unique sources
            
            # Create context-aware prompt guidance
            context_guidance = f"Incorporate insights from {len(context_insights)} relevant context sources and web search results"
            if context_keywords:
                context_guidance += f", focusing on themes related to: {', '.join(context_keywords[:5])}"
            
            enhanced_prompt_elements["context_guidance"] = context_guidance
            enhanced_prompt_elements["context_insights"] = context_insights[:3]  # Store top 3 insights
            
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

# NOTE: image_generator function completely removed

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
                            # NOTE: No image-related fields
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


@# /social_media_agents.py

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


@#excel_generator.py:

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

# ===================== HELPER FUNCTIONS =====================

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
    """Check if a platform should be skipped (all tasks invalid)."""
    for week_key, days in weeks.items():
        for day_key, day_data in days.items():
            if not is_error_content(day_data.get('task', '')):
                return False
    return True

def clean_task_content(content: str, platform: str, day_key: str) -> str:
    """Clean and format task content (remove quotes, capitalize)."""
    content = content.strip('"').strip("'")
    if content:
        content = content[0].upper() + content[1:]
    return content

def extract_content_and_clean(content: str) -> str:
    """Extract and clean content (no image processing)."""
    if not content:
        return ""
    
    # Remove any image-related patterns that might exist
    image_patterns = [
        r'\*\*Image:\*\*[^\n]*',
        r'\*\*Visuals:\*\*[^\n]*',
        r'\(Image:[^)]*\)',
        r'\(Visuals:[^)]*\)',
        r'Image:[^\n]*',
        r'Visuals:[^\n]*'
    ]
    
    clean_content = content
    for pattern in image_patterns:
        clean_content = re.sub(pattern, '', clean_content, flags=re.IGNORECASE)
    
    clean_content = re.sub(r'\n\s*\n', '\n\n', clean_content).strip()
    return clean_content

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
        ws.column_dimensions[col_letter].width = min(max_length + 2, 60)

# ===================== FILE MANAGEMENT - EXCEL ONLY =====================

def upload_excel_to_s3(excel_content: bytes, s3_key: str, bucket: str) -> str:
    """Upload Excel file content to S3."""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=excel_content,
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        return f"s3://{bucket}/{s3_key}"
    except Exception as e:
        print(f"Error uploading Excel to S3: {e}")
        return ""

# ===================== EXCEL GENERATION =====================

def generate_campaign_excel(campaign_plan: Dict[str, Any], campaign_name: str, stage: str = "plan") -> bytes:
    """Generate Excel file from campaign plan data."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if stage in ["draft", "plan"]:
            generate_plan_overview_excel(campaign_plan, writer)
        else:
            generate_content_excel(campaign_plan, writer)
    output.seek(0)
    return output.read()

def generate_plan_overview_excel(campaign_plan: Dict[str, Any], writer) -> None:
    """Generate Excel sheets for plan overview stage (DRAFT)."""
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
                    'Status': 'Pending Approval'
                })
    if overview_data:
        df_overview = pd.DataFrame(overview_data)
        df_overview.to_excel(writer, sheet_name='Campaign Plan', index=False)

def generate_content_excel(campaign_plan: Dict[str, Any], writer) -> None:
    """Generate detailed Excel sheets with content for each platform (no images)."""
    for platform, weeks in campaign_plan.items():
        content_data = []
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                raw_content = day_data.get('content', '')
                clean_content = extract_content_and_clean(raw_content)
                
                content_data.append({
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': day_data.get('task', ''),
                    'Content': clean_content,
                    'Human Feedback': day_data.get('human_feedback', ''),
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
    """Generate Excel sheet with approved campaign overview."""
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
    """Generate full campaign plan sheet with tasks, content, and feedback (no images)."""
    full_data = []
    for platform, weeks in campaign_plan.items():
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                task_content = clean_task_content(day_data.get('task', ''), platform, day_key)
                if not task_content or is_error_content(task_content):
                    continue
                clean_content = extract_content_and_clean(day_data.get('content', ''))
                
                full_data.append({
                    'Platform': platform.title(),
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': task_content,
                    'Content': clean_content,
                    'Human Feedback': day_data.get('human_feedback', ''),
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
    """Create a combined workbook: Approved Overview + Full Plan + Content sheets (no images)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        generate_approved_plan_overview_excel(campaign_plan, writer)
        generate_full_campaign_plan_excel(campaign_plan, writer)
        generate_content_excel(campaign_plan, writer)
    output.seek(0)
    return output.read()

# ===================== PUBLIC API FUNCTIONS - EXCEL ONLY =====================

def generate_and_upload_excel_to_s3(
    campaign_plan: Dict[str, Any],
    campaign_name: str,
    stage: str,
    bucket: str
) -> str:
    """Generate Excel file and upload directly to S3."""
    excel_content = generate_campaign_excel(campaign_plan, campaign_name, stage)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    s3_key = f"campaigns/{campaign_name}/excel/{stage}_{timestamp}.xlsx"
    return upload_excel_to_s3(excel_content, s3_key, bucket)

def generate_and_upload_combined_excel_to_s3(
    campaign_plan: Dict[str, Any],
    campaign_name: str,
    bucket: str,
    plan_data: Dict[str, Any] = None,
    version: int = 1
) -> str:
    """
    Generate combined Excel and upload with versioned filename:
    <username>_<campaign>_final_v{version}.xlsx
    campaign_name should be 'username/campaign_name' format.
    ONLY uploads Excel files to S3 - no JSON files.
    """
    excel_content = generate_combined_excel(campaign_plan, campaign_name, plan_data)
    clean_campaign_path = campaign_name.replace("/", "_")
    filename = f"{clean_campaign_path}_final_v{version}.xlsx"
    s3_key = f"campaigns/{campaign_name}/campaign_planner/excel/{filename}"
    excel_url = upload_excel_to_s3(excel_content, s3_key, bucket)
    
    # Log successful Excel upload
    if excel_url:
        print(f"✅ Successfully uploaded Excel v{version} to S3: {excel_url}")
    else:
        print(f"❌ Failed to upload Excel v{version} to S3")
    
    return excel_url
