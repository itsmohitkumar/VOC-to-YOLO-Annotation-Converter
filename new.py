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
            collection_info = get_collection_info(collection_name, user_id=user_data.get('user_id'))

            if collection_info.get('success') and collection_info.get('metadata', {}).get('count', 0) > 0:
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
