@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    """Retrieve stored responses, injecting image_base64 lists into campaign_plan."""
    try:
        responses = fetch_campaign_responses(username, campaign_name)
        if not responses:
            raise HTTPException(404, f"No campaign found for {username}/{campaign_name}")

        # JSON fields that contain a 'campaign_plan' dict
        json_fields = [
            "plan_response", "approve_response", "feedback_response",
            "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"
        ]

        # 1. Parse them into dicts
        for key in json_fields:
            if key in responses and isinstance(responses[key], str):
                try:
                    responses[key] = json.loads(responses[key])
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse {key}")
                    raise HTTPException(500, f"Invalid JSON in {key}")

        # 2. Fetch all images and group by post_id
        images = list_campaign_images(username, campaign_name)
        images_by_post = {}
        for img in images:
            pid = img["post_id"].lower()
            images_by_post.setdefault(pid, []).append(img["image_base64"])

        # 3. Injection helper
        def inject_images_into(plan_resp: dict):
            cp = plan_resp.get("campaign_plan", {})
            for platform, weeks in cp.items():
                for week_key, days in weeks.items():
                    for day_key, post in days.items():
                        pid = f"{platform.lower()}_{week_key.lower()}_{day_key.lower()}"
                        post["images"] = images_by_post.get(pid, [])

        # 4. Inject into each parsed field
        for key in json_fields:
            if key in responses and isinstance(responses[key], dict):
                inject_images_into(responses[key])

        return responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving responses: {e}")
        raise HTTPException(500, f"Error retrieving responses: {e}")
