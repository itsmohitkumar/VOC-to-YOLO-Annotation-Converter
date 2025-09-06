# ... (rest of the file remains the same)

def update_agentic_campaign_planner(
    username: str,
    campaign_name: str,
    **fields
):
    allowed = {
        "campaign_objective", "campaign_description", "start_date", "end_date",
        "target_audience", "target_audience_location", "target_audience_info",
        "marketing_channels", "campaign_images", "plan_response", "approve_response",
        "feedback_response", "approved_plan", "regeneration_count",  # Corrected spelling
        "approved_plan_v1", "approved_plan_v2", "approved_plan_v3",
        "human_feedback_v1", "human_feedback_v2", "human_feedback_v3"
    }
    to_set = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not to_set:
        return 0

    set_clause = ", ".join([f"{k} = :{k}" for k in to_set.keys()])
    query = text(f"""
        UPDATE agentic_campaign_planner
        SET {set_clause}
        WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
          AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
    """)
    params = {"username": username, "campaign_name": campaign_name, **to_set}
    affected = execute_query(query, params=params, commit=True)
    if affected == 0:
        logger.warning(f"No rows updated for {username}/{campaign_name}")
    return affected

def get_campaign_status(username: str, campaign_name: str) -> dict:
    query = text("""
        SELECT
            approved_plan,
            regeneration_count,  # Corrected spelling
            approved_plan_v1,
            approved_plan_v2,
            approved_plan_v3
        FROM agentic_campaign_planner
        WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
          AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
    """)
    params = {"username": username, "campaign_name": campaign_name}
    result = execute_query(query, params=params, fetch_one=True)
    if result:
        return {
            "approved_plan": bool(result[0]) if result[0] is not None else False,
            "regeneration_count": int(result[1] or 0),
            "has_approved_plan_v1": result[2] is not None,
            "has_approved_plan_v2": result[3] is not None,
            "has_approved_plan_v3": result[4] is not None,
        }
    return {
        "approved_plan": False,
        "regeneration_count": 0,
        "has_approved_plan_v1": False,
        "has_approved_plan_v2": False,
        "has_approved_plan_v3": False,
    }

# ... (rest of the file remains the same)



@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: MultiFeedbackRequest
) -> Dict[str, Any]:
    """
    Feedback batch regeneration (DB-backed):
    - Reads stored plan / feedback from DB (agentic_campaign_planner) instead of S3 JSON.
    - Produces versioned approved_plan_v{batch_version} and updates DB with feedback_response.
    """
    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing enhanced multi-feedback for {campaign_full_name}")

        # ... (Validations and deduplication remain the same)

        # --- Load plans and stored state from DB instead of S3 ---
        # ... (Loading logic remains the same)

        # --- Load feedback tracking from DB (feedback_response) or init default ---
        # ... (Normalization and defaults remain the same)

        # --- Load state (plan.json equivalent) from DB plan_response or fallback ---
        # ... (Remains the same)

        full_plan = copy.deepcopy(campaign_plan)
        details: Dict[str, Any] = {}
        human_feedback_map: Dict[str, str] = {}

        # --- NEW: Pre-check all posts for max attempts to reject batch if any exceed ---
        current_regen_attempts = feedback_dict.get("current_regen_attempts", {})
        max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)
        for fb in deduped_feedbacks:
            pid_norm = fb.post_id.lower()
            current_attempts = current_regen_attempts.get(pid_norm, 0)
            if current_attempts >= max_regen_attempts:
                raise HTTPException(status_code=400, detail=f"Max regeneration attempts reached for post_id '{fb.post_id}'")

        # ... (helper functions remain the same)

        version_number = 0
        processed_post_ids: List[str] = []

        # --- Main feedback loop ---
        # ... (Loop remains mostly the same, but ensure increment only on success)

        # --- Generate Final Plan object ---
        processed_count = len([k for k, v in details.items() if v.get("success")])
        all_attempts = feedback_dict.get("current_regen_attempts", {}) or {}

        # NEW: Incremental batch_version based on existing DB versions
        status = get_campaign_status(username, campaign_name)
        existing_versions = sum([
            status["has_approved_plan_v1"],
            status["has_approved_plan_v2"],
            status["has_approved_plan_v3"]
        ])
        batch_version = existing_versions + 1

        if batch_version > 3:
            raise HTTPException(status_code=400, detail="Maximum feedback versions (3) reached for this campaign")

        # ... (approved_plan_data remains the same)

        # Generate and upload Excel to S3 ONLY
        # ... (Remains the same)

        # Update feedback tracking in database (append to approved_plan_versions)
        # ... (Remains the same)

        # Build response
        # ... (Remains the same)

        # Update database with enhanced feedback response
        try:
            total_regenerations = sum(all_attempts.values())  # Cumulative across posts
            fields_to_update = {
                "feedback_response": json.dumps({
                    "feedback": feedback_dict,
                    "approved_plan": approved_plan_data,
                    "details": details,
                    "enhancements": response["enhancement_features"]
                }, ensure_ascii=False),
                "regeneration_count": total_regenerations  # Updated to cumulative
            }
            # store the whole response into approved_plan_v{n} if v1..v3
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
        logger.error(f"Unexpected error in enhanced submit_feedback: {e}")
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")
