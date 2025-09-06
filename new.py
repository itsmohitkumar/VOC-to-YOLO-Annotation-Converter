@router.post("/{username}/{campaign_name}/approve", response_model=CampaignPlanResponse)
async def approve_campaign_plan(
    username: str,
    campaign_name: str
):
    """
    Approve a campaign plan and generate full content (no images),
    loading the existing plan directly from the database.
    """
    try:
        logger.info(f"Approving campaign plan for user: {username}, campaign: {campaign_name}")

        # Validate user
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(404, f"User '{username}' not found")

        # Validate campaign exists
        user_campaigns = get_user_campaigns(username)
        if not any(c.get("campaign_name", "").lower() == campaign_name.lower() for c in user_campaigns):
            raise HTTPException(404, f"Campaign '{campaign_name}' not found for user '{username}'")

        # Fetch stored plan_response JSON from DB
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses or not responses.get("plan_response"):
            raise HTTPException(404, f"No existing plan_response found for '{username}/{campaign_name}'")

        # Parse plan_response into dict
        stored = responses["plan_response"]
        if isinstance(stored, str):
            try:
                stored = json.loads(stored)
            except Exception:
                raise HTTPException(500, "Invalid JSON in stored plan_response")

        # Validate required fields
        required = ["campaign_name","campaign_objective","campaign_description",
                    "start_date","end_date","target_audience","platforms","campaign_plan"]
        missing = [f for f in required if f not in stored]
        if missing:
            raise HTTPException(400, f"Stored plan missing: {missing}")

        # Normalize audience_info
        tai = stored.get("target_audience_info", [])
        if isinstance(tai, str):
            try:
                tai = json.loads(tai)
            except:
                tai = [e.strip() for e in tai.split(",") if e.strip()]

        # Date validation
        date_info = calculate_date_info(stored["start_date"], stored["end_date"])
        if "error" in date_info:
            raise HTTPException(400, date_info["error"])

        # Validate platforms
        platforms = [p for p in stored.get("platforms", []) if p in ALLOWED_PLATFORMS]
        if not platforms:
            raise HTTPException(400, "No valid platforms in stored plan")

        # Retrieve the plan dict
        campaign_plan = stored["campaign_plan"]
        if isinstance(campaign_plan, str):
            campaign_plan = json.loads(campaign_plan)

        # Build approval state
        approval_state = State(
            campaign_name=stored["campaign_name"],
            campaign_objective=stored["campaign_objective"],
            campaign_description=stored["campaign_description"],
            start_date=stored["start_date"],
            end_date=stored["end_date"],
            target_audience=stored["target_audience"],
            target_audience_info=tai,
            target_audience_location=stored.get("target_audience_location",""),
            base_plan_dict=copy.deepcopy(date_info["week_mapping"]),
            platforms=platforms,
            stage="content_generation",
            plan_approved=True,
            generate_images=False,
            max_regen_attempts=3,
            current_regen_attempts={},
            campaign_plan=campaign_plan,
            messages=[],
            current_step="approval"
        )

        # Generate full content
        final_state = await system_agents.ainvoke(approval_state)
        state_dict = dict(final_state)
        full_plan = state_dict.get("campaign_plan")
        if not full_plan:
            raise HTTPException(404, "Content generation failed after approval")

        # Sanitize images field
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: (sanitize(v) if k.lower() not in 
                             ("images","image_base64","image_s3_key") else [])
                        for k,v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(i) for i in obj]
            return obj

        full_plan = sanitize(full_plan)

        # Upload Excel
        excel_url = generate_and_upload_combined_excel_to_s3(full_plan, f"{username}/{campaign_name}", S3_BUCKET)
        if not excel_url:
            raise HTTPException(500, "Excel upload failed")

        # Store approve_response in DB
        approve_data = {
            **stored,
            "campaign_plan": full_plan,
            "current_step": state_dict.get("current_step","completed"),
            "messages": state_dict.get("messages",[]),
            "stage":"content_generation",
            "plan_approved":True,
            "excel_s3_url":excel_url,
            "content_review_status":"approved"
        }
        update_agentic_campaign_planner(
            username=username,
            campaign_name=campaign_name,
            approve_response=json.dumps(approve_data, ensure_ascii=False),
            approved_plan=True
        )

        return CampaignPlanResponse(
            campaign_name=stored["campaign_name"],
            success=True,
            campaign_plan=full_plan,
            platforms=platforms,
            uploaded_images=[],
            generated_images=[],
            total_images=0,
            content_review_status="approved",
            message=f"Campaign approved. Excel: {excel_url}",
            image_generation_status="skipped",
            target_audience_location=stored.get("target_audience_location","")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving campaign plan: {e}")
        raise HTTPException(500, "Error approving campaign plan") 
