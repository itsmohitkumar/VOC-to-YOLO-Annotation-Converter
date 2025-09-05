def plan_generator(state: State) -> Dict[str, Any]:
    """
    Plan generator agent that creates the initial campaign plan structure with AI-generated tasks.
    This runs in stage 1 to generate the basic plan outline for approval.
    """
    base_plan = state.get("base_plan_dict", {})
    platforms = state.get("platforms", ["instagram", "facebook", "x", "whatsapp", "email", "sms"])
    
    # Map for day_context similar to social_media_agents
    day_context_map = {
        1: "This is the opening/first content piece",
        2: "This is the follow-up content piece",
        3: "This builds momentum from previous content"
    }
    
    campaign_plan = {}
    
    for platform in platforms:
        campaign_plan[platform] = {}
        
        for week_key, week_data in base_plan.items():
            week_num = f"week_{week_key.split('_')[-1]}" if '_' in week_key else "week_1"
            campaign_plan[platform][week_num] = {}
            
            total_days = len(week_data)
            for day_index, day_info in enumerate(week_data, start=1):
                day_key = f"Day_{day_index}"
                # Determine phase exactly as in social_media_agents
                if day_index <= 3:
                    phase = "launch"
                elif day_index <= total_days - 5:
                    phase = "build"
                else:
                    phase = "conclusion"
                # Resolve day_context
                day_context = day_context_map.get(day_index, f"This continues the {phase} phase narrative")
                
                agent_f = PLATFORM_AGENT_MAP.get(platform)
                if agent_f:
                    agent_state = state.copy()
                    agent_state.update({
                        "current_day": day_index,
                        "total_days": total_days,
                        "phase": phase,
                        "day_context": day_context,
                        # ensure no image generation
                        "generate_images": False,
                        "image_generation_enabled": False
                    })
                    try:
                        result = agent_f(agent_state)
                        post = result.get(f"{platform}_post", {})
                        # Extract task_description using our prompt template
                        task_description = post.get('task_description', 
                            f"Generate strategic {platform} task for Day {day_index} of {phase}.")
                        
                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description,
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"Error generating task: {str(e)}",
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No agent found for {platform}",
                        "human_feedback": "",
                        "regeneration_count": 0
                    }
    
    return {
        "messages": ["Campaign plan outline generated with contextual tasks – awaiting approval"],
        "current_step": "plan_generator",
        "campaign_plan": campaign_plan,
        "stage": "plan_generation"
    }



TASK_DESCRIPTION_GENERATION_PROMPT = """
Write a concise single‐line task description (10 to 18 words) that clearly summarizes the content objective for this post.
Requirements (MUST obey):
- Output exactly one sentence only (no extra lines, no explanations).
- Word count must be between 10 and 18 words (inclusive). Count words by splitting on whitespace.
- Do NOT use “…” or any trailing ellipsis—end with a period or exclamation mark.
- Use professional, business-appropriate language. No emojis, no hashtags.
- Highlight the primary benefit or result of the campaign_objective.
- Mention the target audience and include their location as “in {target_audience_location}” when provided.
- Specify the campaign phase and unique day context.
- Be action‐oriented, mentioning both benefit and desired action such as “sign up” or “book a consultation.”
Placeholders:
- campaign_objective: {campaign_objective}
- target_audience: {target_audience}
- target_audience_location: {target_audience_location}
- phase: {phase}
- day_context: {day_context}
Output: a single‐line task description meeting the above constraints (no quotes, no explanation).
"""

