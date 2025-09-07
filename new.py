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
    
    # Generate content with variation check
    previous_variants = state.get("previous_variants", [])
    content = ""
    for retry in range(3):  # Retry up to 3 times if too similar
        try:
            temp = temperature + (retry * 0.05)  # Slight boost per retry
            content = call_bedrock_for_text(
                prompt=base_content_prompt,
                max_tokens=max_tokens,
                temperature=temp
            )
            if check_content_variation(content, previous_variants):
                break
        except Exception as e:
            content = f"Error generating {platform} content: {str(e)}"
            break
    else:
        content += " [NOTE: Variation retry limit reached; content may be similar]"
    
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
