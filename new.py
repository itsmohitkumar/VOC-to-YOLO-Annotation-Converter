@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: "MultiFeedbackRequest"
) -> Dict[str, Any]:
    """
    Enhanced batch feedback endpoint with:
    - Regeneration only for supplied post_ids
    - Logging of each post_id attempted and status
    - Progressive temperature, similarity checks, enhanced seed generation
    """
    import hashlib
    from datetime import datetime

    try:
        campaign_full_name = f"{username}/{campaign_name}"
        logger.info(f"Processing enhanced multi-feedback for {campaign_full_name}")

        # Validate user and campaign
        user_data = get_user_by_username(username)
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        user_campaigns = get_user_campaigns(username)
        if not user_campaigns:
            raise HTTPException(status_code=404, detail=f"No campaigns found for user '{username}'")
        if not any(c.get("campaign_name", "").lower() == campaign_name.lower() for c in user_campaigns):
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")

        # Validate feedback list
        if not feedback_request or not feedback_request.feedbacks:
            raise HTTPException(status_code=400, detail="feedbacks list is required and cannot be empty")

        # Deduplicate and normalize feedback post_ids
        deduped_feedbacks = []
        seen = set()
        for fb in feedback_request.feedbacks:
            pid = (fb.post_id or "").strip()
            if not pid:
                raise HTTPException(status_code=400, detail="Each feedback item must include a non-empty post_id")
            kl = pid.lower()
            if kl in seen:
                logger.info(f"Skipping duplicate post_id: {pid}")
                continue
            seen.add(kl)
            deduped_feedbacks.append(fb)

        if not deduped_feedbacks:
            raise HTTPException(status_code=400, detail="No unique post_ids provided")

        # Load existing plan
        base_prefix = f"campaigns/{username}/{campaign_name}/campaign_planner/response"
        for key in ("approved_plan.json", "plan.json"):
            try:
                obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/{key}")
                stored = json.loads(obj["Body"].read().decode())
                campaign_plan = stored["campaign_plan"]
                break
            except s3_client.exceptions.NoSuchKey:
                continue
        else:
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")

        if isinstance(campaign_plan, str):
            campaign_plan = json.loads(campaign_plan)

        # Feedback tracking state
        try:
            fb_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/feedback.json")
            feedback_dict = json.loads(fb_obj["Body"].read().decode())
        except s3_client.exceptions.NoSuchKey:
            feedback_dict = {
                "feedback_history": [], "current_regen_attempts": {}, "max_regen_attempts": 3,
                "previous_variants": {}
            }

        # Load agent state
        try:
            state_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/plan.json")
            state_dict = json.loads(state_obj["Body"].read().decode())
        except s3_client.exceptions.NoSuchKey:
            state_dict = {"campaign_name": campaign_full_name, "campaign_plan": campaign_plan, "is_regen_required": True}

        full_plan = copy.deepcopy(campaign_plan)
        details = {}
        regeneration_log = []

        # Helper functions
        def classify_feedback_strength(text: str) -> str:
            t = text.lower()
            if any(k in t for k in ["completely rewrite", "start over"]): return "strong"
            if any(k in t for k in ["improve", "enhance", "add"]): return "medium"
            return "light"

        def get_temp(attempt: int, strength: str) -> float:
            base = {"light":0.8,"medium":0.85,"strong":0.9}[strength]
            return base if attempt==1 else (min(base+0.1,0.95) if attempt==2 else 0.95)

        def gen_seed(pid:str, attempt:int, text:str) -> str:
            data = f"{pid}|{attempt}|{text[:50]}|{datetime.utcnow().isoformat()}"
            return hashlib.sha256(data.encode()).hexdigest()

        def similar(new:str, variants:list) -> bool:
            if not variants or not new: return True
            nw = set(new.lower().split())
            for v in variants[-2:]:
                pw = set(v.get("content","").lower().split())
                if len(nw.intersection(pw))/max(len(nw),len(pw),1) > 0.7:
                    return False
            return True

        # Process each feedback item only
        for fb in deduped_feedbacks:
            post_id = fb.post_id.strip()
            pid_norm = post_id.lower()
            fb_text = (fb.feedback_text or "").strip()

            regeneration_log.append({"post_id": post_id, "status": "pending"})

            parts = post_id.split("_")
            if len(parts) < 3:
                details[post_id] = {"success": False, "message": "Invalid post_id format"}
                regeneration_log[-1]["status"] = "failed"
                continue

            platform, wk, dy = parts[0], f"{parts[1]}_{parts[2]}", "_".join(parts[3:]) or "Day_1"
            node = full_plan.get(platform, {}).get(wk, {}).get(dy)
            if not isinstance(node, dict):
                details[post_id] = {"success": False, "message": f"Post ID '{post_id}' not found"}
                regeneration_log[-1]["status"] = "failed"
                continue

            # Attempt count check
            attempts = feedback_dict.setdefault("current_regen_attempts", {})
            curr = attempts.get(pid_norm, 0)
            if curr >= feedback_dict.get("max_regen_attempts",3):
                details[post_id] = {"success": False, "message": "Max regeneration attempts reached"}
                regeneration_log[-1]["status"] = "failed"
                continue

            # Record feedback history
            attempts[pid_norm] = curr + 1
            feedback_dict["feedback_history"].append({
                "post_id": post_id, "feedback_text": fb_text,
                "regen_attempt_number": curr+1, "timestamp": datetime.utcnow().isoformat()
            })

            strength = classify_feedback_strength(fb_text)
            temp = get_temp(curr+1, strength)
            seed = gen_seed(post_id, curr+1, fb_text)
            prev_vars = feedback_dict.setdefault("previous_variants", {}).get(pid_norm, [])

            # Build state for regeneration
            regen_state = {
                **state_dict,
                **feedback_dict,
                "stage": "content_generation",
                "plan_approved": True,
                "current_post_id": post_id,
                "regen_attempt_number": curr+1,
                "human_feedback_text": fb_text,
                "feedback_strength": strength,
                "is_regeneration": True,
                "random_seed": seed,
                "temperature_override": temp,
                "previous_variants": prev_vars,
                "force_variation": True,
                "generate_images": False
            }

            # Retry loop
            new_node = None
            for retry in range(3):
                if retry>0:
                    regen_state["random_seed"] = f"{seed}_retry_{retry}"
                    regen_state["temperature_override"] = min(temp + retry*0.02, 0.98)
                final = await system_agents.ainvoke(regen_state)
                plan_out = final.get("campaign_plan")
                if isinstance(plan_out,str):
                    plan_out = json.loads(plan_out)
                new_node = plan_out.get(platform, {}).get(wk, {}).get(dy)
                if isinstance(new_node, dict) and similar(new_node.get("content",""), prev_vars):
                    break

            if not new_node:
                details[post_id] = {"success": False, "message": "Failed to generate distinct content"}
                regeneration_log[-1]["status"] = "failed"
                continue

            # Merge regenerated node
            merged = copy.deepcopy(new_node)
            merged.update({
                "human_feedback": fb_text,
                "regeneration_count": curr+1,
                "feedback_strength": strength,
                "temperature_used": temp
            })
            # Clean image fields
            for k in ["image_urls","images","image_paths"]:
                merged.pop(k, None)

            full_plan[platform][wk][dy] = merged

            # Store variant
            snapshot = {"content": merged.get("content",""), "timestamp": datetime.utcnow().isoformat()}
            feedback_dict["previous_variants"].setdefault(pid_norm, []).append(snapshot)

            details[post_id] = {"success": True, "message": "Regenerated successfully"}
            regeneration_log[-1]["status"] = "success"

        # Final Excel upload
        excel_url = generate_and_upload_combined_excel_to_s3(full_plan, campaign_full_name, S3_BUCKET, version=max(attempts.values(), default=1))

        return {
            "campaign_name": campaign_full_name,
            "success": True,
            "message": f"Processed {len(deduped_feedbacks)} feedback items, regenerated {sum(1 for d in details.values() if d['success'])}.",
            "campaign_plan": full_plan,
            "details": details,
            "regeneration_log": regeneration_log,
            "excel_s3_url": excel_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in submit_feedback: {e}")
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")
