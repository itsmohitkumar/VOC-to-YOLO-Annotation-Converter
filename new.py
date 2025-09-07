# After successful regeneration:
if isinstance(new_day_node, dict):
    # Always assign the new content
    full_plan[platform_key][week_key][day_key]["content"] = new_day_node.get("content", "")
    full_plan[platform_key][week_key][day_key]["task"] = new_day_node.get("task", full_plan[platform_key][week_key][day_key].get("task", ""))
    # Update feedback and metadata
    full_plan[platform_key][week_key][day_key]["human_feedback"] = fb_text
    full_plan[platform_key][week_key][day_key]["regeneration_count"] = version_number
    full_plan[platform_key][week_key][day_key]["feedback_strength"] = feedback_strength
    full_plan[platform_key][week_key][day_key]["temperature_used"] = temperature
    # ...plus any additional metadata needed
else:
    # Existing fallback is OK, but must ensure new content gets in
    # It's safer to force a direct assignment here as well if possible
    full_plan[platform_key][week_key][day_key]["content"] = final_state_dict.get("content", "")


human_feedback = state.get("human_feedback_text", "")
if human_feedback:
    regen_attempt = state.get("regen_attempt_number", 1)
    base_content_prompt += (
        f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\n"
        "Incorporate this feedback to improve the post and ensure the new version is distinctly different."
    )


# After agent returns dict:
agent_plan = final_state_dict.get("campaign_plan")
if isinstance(agent_plan, dict):
    new_day_node = agent_plan.get(platform_key, {}).get(week_key, {}).get(day_key)
    # Always update only that node using the extracted content


if not full_plan[platform_key][week_key][day_key]["content"]:
    full_plan[platform_key][week_key][day_key]["content"] = "[ERROR] Regeneration did not produce varied content"





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

    # Validate post exists in full_plan
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

    # Attempt limits
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

    # Enhanced regeneration input state
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
    new_day_node = None
    final_state_dict = {}

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
                # If agent didn't return a day node, accept agent output if no error
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

    # ==== FIXED MERGE LOGIC ====
    # Always assign the newly generated content and task into the plan!
    if isinstance(new_day_node, dict):
        for k in ("task", "content", "caption", "headline", "cta", "hook", "angle", "hashtags", "title", "body", "notes"):
            if k in new_day_node:
                full_plan[platform_key][week_key][day_key][k] = new_day_node[k]
        full_plan[platform_key][week_key][day_key]["human_feedback"] = fb_text
        full_plan[platform_key][week_key][day_key]["regeneration_count"] = version_number
        full_plan[platform_key][week_key][day_key]["feedback_strength"] = feedback_strength
        full_plan[platform_key][week_key][day_key]["temperature_used"] = temperature
    else:
        full_plan[platform_key][week_key][day_key]["content"] = final_state_dict.get("content", "")
        full_plan[platform_key][week_key][day_key]["human_feedback"] = fb_text
        full_plan[platform_key][week_key][day_key]["regeneration_count"] = version_number
        full_plan[platform_key][week_key][day_key]["feedback_strength"] = feedback_strength
        full_plan[platform_key][week_key][day_key]["temperature_used"] = temperature
        # Defensive: fallback if no content
        if not full_plan[platform_key][week_key][day_key]["content"]:
            full_plan[platform_key][week_key][day_key]["content"] = "[ERROR] Regeneration did not produce varied content"

    # Store variant for future similarity checking
    pv_map = feedback_dict.setdefault("previous_variants", {})
    pv_list = pv_map.get(pid_norm, [])
    variant_snapshot = {
        k: full_plan[platform_key][week_key][day_key].get(k)
        for k in ("content", "caption", "headline", "cta", "hook", "angle", "hashtags", "title", "body", "notes")
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






# Add human feedback if present
human_feedback = state.get("human_feedback_text", "")
if human_feedback:
    regen_attempt = state.get("regen_attempt_number", 1)
    base_content_prompt += (
        f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\n"
        "Incorporate this feedback to improve the post and ensure the new version is distinctly different."
    )


if regen_attempt > 1:
    base_content_prompt = enhance_prompt(base_content_prompt, state)

