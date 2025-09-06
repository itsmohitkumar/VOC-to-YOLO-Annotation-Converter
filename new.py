@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    """
    Retrieve stored responses, injecting image_base64 lists into campaign_plan.
    """
    try:
        # 1. Fetch raw DB responses
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses:
            raise HTTPException(404, f"No campaign found for {username}/{campaign_name}")

        # Keys that contain a JSON with campaign_plan
        json_fields = [
            "plan_response", "approve_response", "feedback_response",
            "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"
        ]

        # 2. Parse each into dict
        for key in json_fields:
            val = responses.get(key)
            if isinstance(val, str):
                try:
                    responses[key] = json.loads(val)
                except Exception:
                    logger.error(f"Invalid JSON in {key}")
                    raise HTTPException(500, f"Invalid JSON in {key}")

        # 3. Fetch images from DB
        images = list_campaign_images(username, campaign_name)
        images_by_post = {}
        for img in images:
            pid = img["post_id"].lower()
            images_by_post.setdefault(pid, []).append(img["image_base64"])
        logger.debug(f"Images by post map: {images_by_post}")

        # 4. Inject helper
        def inject(plan_resp: dict):
            cp = plan_resp.get("campaign_plan", {})
            for platform, weeks in cp.items():
                for week, days in weeks.items():
                    for day, post in days.items():
                        pid = f"{platform.lower()}_{week.lower()}_{day.lower()}"
                        post["images"] = images_by_post.get(pid, [])

        # 5. Inject into each
        for key in json_fields:
            pr = responses.get(key)
            if isinstance(pr, dict) and "campaign_plan" in pr:
                inject(pr)

        return responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving responses: {e}")
        raise HTTPException(500, f"Error retrieving responses: {e}")
