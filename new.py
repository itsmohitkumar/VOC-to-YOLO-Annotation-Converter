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
            campaign_plan = campaign_plan.dict()

        # ========================= Image sanitization (minimal since no images) =========================
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
