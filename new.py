from typing import Dict, Any
from src.models import State
from src.llm import call_bedrock_for_text

# Templates for task and content (replace with your actual prompt templates)
TASK_PROMPT_TEMPLATE = (
    "Create a concise task description for campaign objective: '{objective}', "
    "audience: '{audience}', location: '{audience_location}', "
    "phase: '{phase}', context: '{day_context}'."
)

CONTENT_PROMPT_TEMPLATES = {
    "instagram": "...your Instagram prompt template here...",
    "facebook": "...your Facebook prompt template here...",
    "x": "...your X/Twitter prompt template here...",
    "whatsapp": "...your WhatsApp prompt template here...",
    "email": "...your Email prompt template here...",
    "sms": "...your SMS prompt template here...",
}

def get_dynamic_temperature(state: State) -> float:
    """Calculate temperature based on feedback strength and regeneration count."""
    strength = state.get("feedback_strength", "medium")
    attempt = state.get("regen_attempt", 1)
    base_temps = {"light": 0.75, "medium": 0.80, "strong": 0.85}
    base_temp = base_temps.get(strength, 0.80)

    if attempt == 1:
        return base_temp
    elif attempt == 2:
        return min(base_temp + 0.10, 0.90)
    else:  # 3rd+ attempt
        return min(base_temp + 0.15, 0.95)

def enhance_prompt(prompt: str, state: State) -> str:
    """Add directives for regeneration with variation enforcement."""
    lines = [
        f"--- Regeneration attempt {state.get('regen_attempt', 1)} ---"
    ]
    strength = state.get("feedback_strength", "medium")
    if strength == "strong":
        lines.append("Create content that is completely different from prior versions.")
    elif strength == "medium":
        lines.append("Make substantial changes while keeping message aligned.")
    else:
        lines.append("Make meaningful improvements preserving core style.")

    if state.get("previous_variants"):
        lines.append(f"Avoid similarities with past {len(state['previous_variants'])} versions.")

    if state.get("force_variation", False):
        lines.append("Enforce maximum variation in this generation.")

    return prompt + "\n" + "\n".join(lines)

def generate_task_description(state: State, phase: str, day_context: str) -> str:
    """Generate task description with slight temperature adjustment."""
    prompt = TASK_PROMPT_TEMPLATE.format(
        objective=state.get("campaign_objective", ""),
        audience=state.get("target_audience", ""),
        audience_location=state.get("target_audience_location", ""),
        phase=phase, day_context=day_context
    )
    temp = get_dynamic_temperature(state) * 0.90
    try:
        desc = call_bedrock_for_text(prompt, max_tokens=50, temperature=temp).strip()
        if not desc:
            desc = call_bedrock_for_text(prompt, max_tokens=40, temperature=temp + 0.10).strip()
        return desc if len(desc) <= 80 else desc[:77] + "..."
    except Exception:
        return f"Generate task for {state.get('campaign_objective', '').lower()}"

def create_social_media_post(state: State, platform: str) -> Dict[str, Any]:
    """Generic social media post creator with regeneration support."""
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    phase = ("launch" if current_day <= 3 else "build" if current_day <= total_days - 5 else "conclusion")
    
    day_context_map = {1: "opening content", 2: "follow-up content", 3: "momentum building content"}
    day_context = day_context_map.get(current_day, f"content in {phase} phase")

    task_description = generate_task_description(state, phase, day_context)

    base_content_prompt = CONTENT_PROMPT_TEMPLATES.get(platform, "").format(
        day=current_day,
        total_days=total_days,
        objective=state.get("campaign_objective", ""),
        theme=state.get("campaign_theme", ""),
        audience=state.get("target_audience", ""),
        audience_location=state.get("target_audience_location", ""),
        phase=phase,
        web_context=state.get("search_results", "")[:500] if state.get("search_results") else "No web context",
        keywords=', '.join(state.get("optimized_prompts", {}).get("context_keywords", [])),
        guidance=state.get("optimized_prompts", {}).get("context_guidance", "")
    )

    human_feedback = state.get("human_feedback_text")
    if human_feedback:
        base_content_prompt += f"\n\nIncorporate this feedback: {human_feedback}"

    regen_attempt = state.get("regen_attempt", 1)
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)

    temperature = get_dynamic_temperature(state)

    try:
        content = call_bedrock_for_text(base_content_prompt, max_tokens=1000 if platform != "email" else 1200, temperature=temperature)
    except Exception as e:
        content = f"Error generating content: {e}"

    post_key = f"{platform}_post"

    post = {
        "task_description": task_description,
        "content": content,
        "regeneration_metadata": {
            "attempt": regen_attempt,
            "temperature": temperature,
            "feedback": human_feedback,
        },
    }

    return {
        post_key: post,
        "messages": [f"Generated {platform} post day {current_day} attempt {regen_attempt} at temp {temperature:.2f}"],
        "current_step": f"create_{platform}_post",
    }

# Each platform's create_post simply calls the generic function with the platform name:
def create_instagram_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "instagram")

def create_facebook_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "facebook")

def create_x_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "x")

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "whatsapp")

def create_email_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "email")

def create_sms_post(state: State) -> Dict[str, Any]:
    return create_social_media_post(state, "sms")
