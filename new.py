def create_social_media_post(state: State, platform: str) -> Dict[str, Any]:
    """Generic social media post creator with regeneration support."""
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    
    # Determine campaign phase
    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"
    
    day_context_map = {
        1: "This is the opening/first content piece",
        2: "This is the follow-up content piece", 
        3: "This builds momentum from previous content"
    }
    day_context = day_context_map.get(current_day, f"This continues the {phase} phase narrative")
    
    # Generate task description
    task_description = generate_task_description(state, phase, day_context)
    
    # Build base content prompt
    base_content_prompt = CONTENT_PROMPT_TEMPLATES.get(platform, "").format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=state.get("campaign_objective", ""),
        campaign_theme=state.get("campaign_theme", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        web_search_results=state.get("search_results", "")[:500] if state.get("search_results") else "No web search context available",
        context_keywords=', '.join(state.get("optimized_prompts", {}).get("context_keywords", [])),
        context_guidance=state.get("optimized_prompts", {}).get("context_guidance", "")
    )
    
    # Add human feedback if present
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)  # Initialize outside try-except and before use
    
    if human_feedback:
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post and ensure the new version is distinctly different."
    
    # Apply enhanced variation for regenerations
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)
    
    # Get dynamic temperature
    temperature = get_dynamic_temperature(state)
    
    # Platform-specific max tokens
    max_tokens_map = {
        "instagram": 1000,
        "facebook": 1000,
        "x": 500,
        "whatsapp": 800,
        "email": 1200,
        "sms": 300
    }
    max_tokens = max_tokens_map.get(platform, 1000)
    
    # Generate content with variation check (increased retries and temperature boost)
    previous_variants = state.get("previous_variants", [])
    content = ""
    max_retries = 5  # Increased from 3 for better variation
    for retry in range(max_retries):
        try:
            temp = temperature + (retry * 0.1)  # Stronger boost per retry (up from 0.05)
            # Add extra entropy to force variation
            entropy_prompt = f"\n\nVARIATION BOOST: Use a completely new angle, tone, and structure. Random seed: {random.randint(1, 1000000)}"
            full_prompt = base_content_prompt + entropy_prompt
            content = call_bedrock_for_text(
                prompt=full_prompt,
                max_tokens=max_tokens,
                temperature=temp
            ).strip()
            if check_content_variation(content, previous_variants):
                break
        except Exception as e:
            logger.error(f"Error generating {platform} content (retry {retry}, attempt {regen_attempt}): {str(e)}")
            content = f"Error generating content: {str(e)}"
            break
    else:
        # Better fallback: Generate a simple varied version manually if all retries fail
        content = f"Rewritten post with changed tone: [Original feedback applied manually] - {human_feedback[:50]}... (Automated variation failed, but content updated.)"
        logger.warning(f"Variation retry limit reached for {platform}; using manual fallback content.")
    
    # Build post response
    post_key = f"{platform}_post"
    post = {
        "task_description": task_description,
        "content": content,
        "regeneration_metadata": {
            "attempt": regen_attempt,
            "temperature_used": temperature,
            "feedback_incorporated": bool(human_feedback),
            "feedback_strength": state.get("feedback_strength", "medium"),
            "seed": state.get("random_seed", ""),
            "generation_timestamp": time.time()
        }
    }
    
    return {
        post_key: post,
        "messages": [f"Enhanced {platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f} using AWS Bedrock"],
        "current_step": f"create_{platform}_post",
        "content": content,  # Direct content access for state extraction
        "task_description": task_description  # Direct task access for state extraction
    }




# Inside the for fb loop, after the retry loop
if not successful_regeneration:
    details[post_id] = {"success": False, "message": f"Failed to generate sufficiently different content after {max_retry_attempts} attempts"}
    continue

# Process successful regeneration / merge
merged_node = full_plan[platform_key][week_key].get(day_key, {})  # Start with existing node
if isinstance(new_day_node, dict):
    merged_node.update(new_day_node)  # Merge new fields
else:
    # Flexible fallback extraction from final_state_dict
    fallback_keys = (
        "task", "content", "caption", "headline", "cta",
        "hook", "angle", "hashtags", "title", "body", "notes"
    )
    for k in fallback_keys:
        if k in final_state_dict:
            merged_node[k] = final_state_dict[k]
    # If still no content, set a default varied version
    if "content" not in merged_node or not merged_node["content"]:
        merged_node["content"] = f"Regenerated content with updated tone: {fb_text[:100]}... (Fallback due to variation issues)."

# Clean up any image-related fields (kept)
image_related_keys = ["image_path_s3", "image_paths", "image_urls", "images", "image_prompt"]
for img_key in image_related_keys:
    if img_key in merged_node:
        merged_node[img_key] = []

merged_node["human_feedback"] = fb_text
merged_node["regeneration_count"] = version_number
merged_node["feedback_strength"] = feedback_strength
merged_node["temperature_used"] = temperature
full_plan[platform_key][week_key][day_key] = merged_node

# Store variant for future similarity checking (unchanged)
# ...

