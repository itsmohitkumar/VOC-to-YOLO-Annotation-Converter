```python
# In src/llm/prompts.py

DAILY_CONTENT_STRATEGY_PROMPT = """
Generate content ideas for day {current_day} of a {total_days}-day campaign:
Campaign Theme: {campaign_theme}
Campaign Objective: {campaign_objective}
Target Audience: {target_audience}
Location: {location}
Platform: {platform}
Provide content suggestions that:
- Align with the campaign progression (launch/build/climax/conclusion)
- Match the platform's best practices
- Engage the target audience effectively
- Support the campaign objective
- Reflect the campaign theme authentically
Format as JSON:
{{
    "content_idea": "specific content suggestion for this day",
    "content_type": "post type (video, image, text, etc.)",
    "engagement_strategy": "how to maximize engagement",
    "timing_recommendation": "best time to post",
    "campaign_phase": "launch/build/climax/conclusion"
}}
"""
```

```python
# In src/campaign_agent/system_agents.py

from src.llm.prompts import DAILY_CONTENT_STRATEGY_PROMPT

def daily_strategy_generator(state: State) -> Dict[str, Any]:
    """Generate daily content strategy JSON."""
    prompt = DAILY_CONTENT_STRATEGY_PROMPT.format(
        current_day=state.get("current_day", 1),
        total_days=state.get("total_days", 7),
        campaign_theme=state.get("campaign_theme", ""),
        campaign_objective=state.get("campaign_objective", ""),
        target_audience=state.get("target_audience", ""),
        location=state.get("target_audience_location", ""),
        platform=state.get("platform", "")
    )
    strategy_json = call_bedrock_for_text(
        prompt=prompt,
        max_tokens=300,
        temperature=0.7
    )
    return {
        "messages": ["Daily strategy generated"],
        "current_step": "daily_strategy_generator",
        "daily_strategy": strategy_json
    }
```

```python
# In src/agent/graph.py (wiring the new node)

from src.campaign_agent.system_agents import daily_strategy_generator

# ... existing edges ...
graph.add_edge("prompt_optimization", "daily_strategy_generator")
graph.add_node("daily_strategy_generator", daily_strategy_generator)
graph.add_edge("daily_strategy_generator", "text_generator")
```

```python
# In src/campaign_agent/system_agents.py (consuming the strategy)

def text_generator(state: State) -> Dict[str, Any]:
    optimized = state.get("optimized_prompts", {})
    prompt = (
        f"Objective: {optimized.get('objective')}\n"
        f"Description: {optimized.get('description')}\n"
        f"Audience: {optimized.get('audience')}\n"
        f"Context Guidance: {optimized.get('context_guidance')}\n"
    )
    # Append daily strategy if available
    if state.get("daily_strategy"):
        try:
            strat = json.loads(state["daily_strategy"])
            prompt += (
                "\nDaily Strategy:\n"
                f"- Idea: {strat.get('content_idea')}\n"
                f"- Type: {strat.get('content_type')}\n"
                f"- Engagement: {strat.get('engagement_strategy')}\n"
                f"- Timing: {strat.get('timing_recommendation')}\n"
                f"- Phase: {strat.get('campaign_phase')}\n"
            )
        except json.JSONDecodeError:
            pass

    generated_text = call_bedrock_for_text(prompt=prompt, max_tokens=2000, temperature=0.7)
    return {
        "messages": ["Text generation completed using AWS Bedrock"],
        "current_step": "text_generator",
        "generated_text": generated_text
    }
```

[1](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/42012257/3b7a7c38-422b-4f23-8b02-024b707c0a84/paste.txt)
