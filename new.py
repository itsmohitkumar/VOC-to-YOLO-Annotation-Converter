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
    marketing_channels: List[str] = Form(default=["instagram", "facebook", "email", "whatsapp", "sms"])
):
    """
    Create a campaign plan with customizable marketing channels (no images).
    """
    try:
        logger.info(f"Starting request validation for user: {username}, campaign: {campaign_name}")

        # ========================= Input validations =========================

        # Normalize and validate marketing channels (enhanced splitting)
        processed_channels: List[str] = []
        if marketing_channels:
            for channel in marketing_channels:
                # Split on commas regardless, to handle 'instagram,sms'
                if isinstance(channel, str):
                    split_channels = [c.strip().lower() for c in channel.split(',') if c.strip()]
                    processed_channels.extend(split_channels)
                else:
                    processed_channels.append(str(channel).strip().lower())

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
        audience_emails: List[str] = []
        if target_audience_info:
            processed_audience_info = target_audience_info.strip()
            if processed_audience_info:
                audience_emails = [
                    email.strip().strip('"').strip("'")
                    for email in processed_audience_info.split(",")
                    if email.strip()
                ]
                email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
                for email in audience_emails:
                    if not email_pattern.match(email):
                        raise HTTPException(status_code=400, detail=f"Invalid email format: {email}")
                logger.info(f"Validated {len(audience_emails)} email addresses")
            else:
                logger.info("target_audience_info was provided but empty → skipping email validation")
        else:
            logger.info("No target_audience_info provided → skipping email validation")

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

        # ======================================== Retrieve context from vector database ========================================
        logger.info(f"Retrieving context from vector database for campaign: {campaign_full_name}")
        vector_context: List[Dict[str, Any]] = []
        try:
            search_queries = [
                f"{campaign_objective} {target_audience}",
                f"{campaign_description}",
                f"campaign planning {target_audience}"
            ]
            collection_name = campaign_full_name
            collection_info = get_collection_info(collection_name, user_id=user_data.get('user_id'))... if collection_info.get('success') and collection_info.get('metadata', {}).get('count', 0) > 0:
                logger.info(f"Found vector database collection for user: {collection_name}")
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
        except Exception as e:
            logger.error(f"Error retrieving context from vector database: {e}")
            raise HTTPException(status_code=500, detail=f"Error accessing knowledge base for user '{username}'.")

        if not vector_context:
            logger.error(f"No relevant context retrieved for campaign: {campaign_full_name}")
            raise HTTPException(
                status_code=400,
                detail="No relevant content found in knowledge base for this campaign."
            )

        # ================================ Agentic workflow and generation ================================
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
            generate_images=False,  # Images removed
            stage="plan_generation",
            plan_approved=False
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

        generated_images: List[Dict[str, Any]] = []  # Empty since images removed
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
            content_review_status = "error"... # Upload Excel to S3
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

        # Prepare and store plan.json (no images)
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
            "generated_images": generated_images,
            "image_generation_status": image_generation_status,
            "content_review_status": content_review_status,
            "excel_s3_url": excel_s3_url
        }

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
            plan_response=json.dumps(plan_data, ensure_ascii=False)
        )

        total_images = len(generated_images)  # Always 0
        message_parts = [f"Campaign plan generated successfully. Excel file: {excel_s3_url}"]
        if content_review_status in ["approved", "approved_with_suggestions"]:
            message_parts.append("Content review completed successfully.")
        response_message = " ".join(message_parts)

        return CampaignPlanResponse(
            campaign_name=campaign_full_name,
            success=True,
            message=response_message,
            campaign_plan=campaign_plan,              
            platforms=unique_marketing_channels,
            uploaded_images=[],  # Explicit empty list to satisfy model
            generated_images=[],  # Explicit empty list to satisfy model
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
    """
    Approve a campaign plan and generate full content (no images).
    """
    try:
        logger.info(f"Approving campaign plan for user: {username}, campaign: {campaign_name}")

        # ========================= Input validations =========================
        # Validate user
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User with username '{username}' not found.")

        # Validate campaign existence for user
        user_campaigns = get_user_campaigns(username)
        campaign_exists_flag = any(
            (campaign.get("campaign_name", "") or "").lower() == campaign_name.lower()
            for campaign in user_campaigns
        )
        if not campaign_exists_flag:
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'.")

        # Load existing plan.json from S3 (must exist before approval)
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
            raise HTTPException(status_code=500, detail="Failed to read stored campaign plan")... # Validate essential fields from stored plan
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

        # ======================= Build approval state =========================
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
            current_step="approval"
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
            campaign_plan = campaign_plan.dict()... # ========================= Image sanitization (minimal since no images) =========================
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
        campaign_plan = _sanitize_image_fields(campaign_plan)

        # ========================= Upload combined Excel to S3 =========================
        excel_s3_url = generate_and_upload_combined_excel_to_s3(
            campaign_plan,
            campaign_full_name,
            S3_BUCKET
        )
        if not excel_s3_url:
            raise HTTPException(status_code=500, detail="Failed to upload Excel file to S3")

        # ========================= Build response & store approved plan =========================
        total_images = 0

        # Build a user-facing message (no image generation info)
        message_parts = [
            f"Campaign plan approved and full content generated successfully. Excel file: {excel_s3_url}"
        ]
        message_text = " ".join(message_parts)

        # Prepare and store approved_plan.json
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
            "message": message_text,
            "image_generation_status": image_generation_status,
            "content_review_status": "approved"
        }

        update_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            approve_response=json.dumps(approved_plan_data, ensure_ascii=False),
            approved_plan=True
        )

        # Build response compatible with CampaignPlanResponse
        return CampaignPlanResponse(
            campaign_name=campaign_full_name,
            success=True,
            campaign_plan=campaign_plan,              
            platforms=platforms,
            uploaded_images=[],  # Explicit empty list to satisfy model
            generated_images=[],  # Explicit empty list to satisfy model
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
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")... if not feedback_request or not feedback_request.feedbacks:
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
        processed_post_ids: List[str] = []... def classify_feedback_strength(feedback_text: str) -> str:
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
            human_feedback_map[post_id] = fb_text... version_number = current_regen_attempts.get(pid_norm, 1)
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

            full_plan[platform_key][week_key][day_key] = merged_node... # Store variant for future similarity checking
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
