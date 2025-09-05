def classify_feedback_strength(feedback_text: str) -> str:
    """
    Classify feedback strength for targeted regeneration.
    """
    t = feedback_text.lower()
    if any(k in t for k in ["rewrite", "completely", "start over"]):
        return "strong"
    if any(k in t for k in ["improve", "enhance", "add", "include"]):
        return "medium"
    return "light"

def make_seed(post_id: str, attempt: int, feedback_text: str) -> str:
    """
    Generate a unique SHA-256 seed for variation.
    """
    ts = datetime.utcnow().isoformat()
    seed_input = f"{post_id}|{attempt}|{feedback_text[:50]}|{ts}"
    return hashlib.sha256(seed_input.encode()).hexdigest()

def content_similarity_check(new_content: str, previous_variants: List[Dict]) -> bool:
    """
    Ensure new content differs from recent variants.
    """
    if not previous_variants or not new_content:
        return True
    new_words = set(new_content.lower().split())
    for variant in previous_variants[-2:]:
        old_words = set(variant.get("content", "").lower().split())
        overlap = len(new_words & old_words) / max(len(new_words), len(old_words), 1)
        if overlap > 0.7:
            return False
    return True

def safe_truncate(value: str, max_length: int = 8000) -> str:
    """
    Truncate string to fit DB column size, preventing 'data would be truncated' error.
    Adjust max_length based on your actual DB schema (e.g., varchar(8000)).
    """
    if len(value) > max_length:
        truncated = value[:max_length - 3] + "..."
        logger.warning(f"Truncated string from {len(value)} to {max_length} chars to avoid DB truncation error.")
        return truncated
    return value

@router.post("/{username}/{campaign_name}/feedback")
async def submit_feedback(
    username: str,
    campaign_name: str,
    feedback_request: "MultiFeedbackRequest"
) -> Dict[str, Any]:
    """
    Enhanced batch feedback endpoint:
    - Progressive temperature increases for attempts 1–3
    - SHA-256 seed generation for variation
    - Content similarity checks and retries
    - Only regenerates the specific post
    - Only uploads versioned Excel to S3
    """
    campaign_full = f"{username}/{campaign_name}"
    logger.info(f"Processing feedback for {campaign_full}")

    # Validate user and campaign
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(404, "User not found")
    campaigns = get_user_campaigns(username)
    if campaign_name not in [c["campaign_name"] for c in campaigns]:
        raise HTTPException(404, "Campaign not found")

    # Deduplicate feedback items
    deduped = []
    seen = set()
    for fb in getattr(feedback_request, "feedbacks", []):
        pid = (fb.post_id or "").strip()
        if pid and pid.lower() not in seen:
            seen.add(pid.lower())
            deduped.append(fb)
    if not deduped:
        raise HTTPException(400, "No valid feedback items")

    # Load existing plan
    base_prefix = f"campaigns/{username}/{campaign_name}/campaign_planner/response"
    plan_data = None
    for key in ("approved_plan.json", "plan.json"):
        try:
            obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/{key}")
            plan_data = json.loads(obj["Body"].read().decode("utf-8"))
            break
        except s3_client.exceptions.NoSuchKey:
            continue
    if not plan_data or "campaign_plan" not in plan_data:
        raise HTTPException(404, "Plan not found")
    full_plan = copy.deepcopy(plan_data["campaign_plan"])

    # Load or initialize feedback store
    try:
        obj = s3_client.get_object(Bucket=S3_BUCKET, Key=f"{base_prefix}/feedback.json")
        fb_store = json.loads(obj["Body"].read().decode("utf-8"))
    except s3_client.exceptions.NoSuchKey:
        fb_store = {"current_attempts": {}, "history": [], "previous_variants": {}}

    details = {}
    for fb in deduped:
        pid = fb.post_id.strip()
        pnorm = pid.lower()
        text = (fb.feedback_text or "").strip()

        # Validate post exists in plan
        parts = pid.split("_")
        if len(parts) < 4 or parts[0] not in full_plan:
            details[pid] = {"success": False, "message": "Invalid post_id"}
            continue

        # Check and increment attempt count
        attempts = fb_store["current_attempts"].get(pnorm, 0)
        if attempts >= 3:
            details[pid] = {"success": False, "message": "Max attempts reached"}
            continue
        attempts += 1
        fb_store["current_attempts"][pnorm] = attempts
        fb_store["history"].append({
            "post_id": pid,
            "feedback_text": text,
            "attempt": attempts,
            "timestamp": datetime.utcnow().isoformat()
        })

        # Parse keys safely
        platform = parts[0]
        week_key = f"{parts[1]}_{parts[2]}"
        day_key = "_".join(parts[3:])

        # Ensure structure exists in full_plan
        if platform not in full_plan:
            full_plan[platform] = {}
        if week_key not in full_plan[platform]:
            full_plan[platform][week_key] = {}
        if day_key not in full_plan[platform][week_key]:
            full_plan[platform][week_key][day_key] = {}

        # Prepare regeneration state
        seed = make_seed(pid, attempts, text)
        regen_state = {
            **plan_data,
            "stage": "content_generation",
            "plan_approved": True,
            "current_post_id": pid,
            "is_regeneration": True,
            "regen_attempt_number": attempts,
            "human_feedback_text": text,
            "feedback_strength": classify_feedback_strength(text),
            "force_variation": True,
            "random_seed": seed,
            "previous_variants": fb_store["previous_variants"].get(pnorm, [])
        }

        # Invoke regeneration with retries on similarity
        new_content = ""
        for retry in range(3):
            if retry > 0:
                regen_state["random_seed"] = seed + f"_r{retry}"
            result = await system_agents.ainvoke(regen_state)
            new_plan = result.get("campaign_plan", {})
            # Extract the specific node safely
            if platform in new_plan and week_key in new_plan[platform] and day_key in new_plan[platform][week_key]:
                node = new_plan[platform][week_key][day_key]
                new_content = node.get("content", "")
                if content_similarity_check(new_content, fb_store["previous_variants"].get(pnorm, [])):
                    # Merge the regenerated node into full_plan
                    full_plan[platform][week_key][day_key].update(node)
                    break
        else:
            details[pid] = {"success": False, "message": "Failed to vary content"}
            continue

        # Store new variant content for future similarity checks
        fb_store["previous_variants"].setdefault(pnorm, []).append({"content": new_content})
        details[pid] = {"success": True, "attempts": attempts}

    # Upload versioned Excel to S3 only
    version = max(fb_store["current_attempts"].values(), default=1)
    excel_url = generate_and_upload_combined_excel_to_s3(full_plan, campaign_full, S3_BUCKET, version=version)

    # Persist updated plan and feedback in DB only (no JSON to S3)
    update_agentic_campaign_planner(
        username=username,
        campaign_name=campaign_name,
        approved_plan=safe_truncate(json.dumps({"campaign_plan": full_plan}, ensure_ascii=False)),
        feedback_response=safe_truncate(json.dumps(fb_store, ensure_ascii=False)),
        regeneration_count=version
    )

    return {
        "campaign_name": campaign_full,
        "success": True,
        "campaign_plan": full_plan,
        "details": details,
        "excel_s3_url": excel_url
    }
