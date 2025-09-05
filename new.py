
from typing import Dict, Any
from src.models import State
from src.llm.prompts import (
    INSTAGRAM_CONTENT_GENERATION_PROMPT,
    FACEBOOK_CONTENT_GENERATION_PROMPT,
    X_CONTENT_GENERATION_PROMPT,
    WHATSAPP_CONTENT_GENERATION_PROMPT,
    EMAIL_CONTENT_GENERATION_PROMPT,
    SMS_CONTENT_GENERATION_PROMPT,
    TASK_DESCRIPTION_GENERATION_PROMPT
)

import sys
import os
import hashlib
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.llm.bedrock import call_bedrock_for_text

# Templates for task and content
TASK_PROMPT_TEMPLATE = TASK_DESCRIPTION_GENERATION_PROMPT

CONTENT_PROMPT_TEMPLATES = {
    "instagram": INSTAGRAM_CONTENT_GENERATION_PROMPT,
    "facebook": FACEBOOK_CONTENT_GENERATION_PROMPT,
    "x": X_CONTENT_GENERATION_PROMPT,
    "whatsapp": WHATSAPP_CONTENT_GENERATION_PROMPT,
    "email": EMAIL_CONTENT_GENERATION_PROMPT,
    "sms": SMS_CONTENT_GENERATION_PROMPT,
}

def get_dynamic_temperature(state: State) -> float:
    """Calculate temperature based on feedback strength and regeneration count."""
    strength = state.get("feedback_strength", "medium")
    attempt = state.get("regen_attempt_number", 1)
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
    attempt = state.get("regen_attempt_number", 1)
    lines = [
        f"--- REGENERATION ATTEMPT {attempt} ---"
    ]
    
    strength = state.get("feedback_strength", "medium")
    if strength == "strong":
        lines.append("IMPORTANT: Create content that is completely different from prior versions.")
    elif strength == "medium":
        lines.append("IMPORTANT: Make substantial changes while keeping message aligned.")
    else:
        lines.append("IMPORTANT: Make meaningful improvements preserving core style.")
    
    if state.get("previous_variants"):
        lines.append(f"NOTE: Avoid similarities with past {len(state['previous_variants'])} versions.")
    
    if state.get("force_variation", False):
        lines.append("CRITICAL: Enforce maximum variation in this generation.")
    
    # Add seed-based variation cue
    random_seed = state.get("random_seed", "")
    if random_seed:
        seed_hash = int(hashlib.md5(random_seed.encode()).hexdigest()[:8], 16)
        styles = ["bold", "subtle", "innovative", "classic", "modern", "authentic", "dynamic", "engaging"]
        style = styles[seed_hash % len(styles)]
        lines.append(f"STYLE: Use a {style} approach for this variation.")
    
    return prompt + "\n\n" + "\n".join(lines)

def generate_task_description(state: State, phase: str, day_context: str) -> str:
    """Generate task description with slight temperature adjustment."""
    prompt = TASK_PROMPT_TEMPLATE.format(
        campaign_objective=state.get("campaign_objective", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        day_context=day_context
    )
    
    temp = get_dynamic_temperature(state) * 0.90
    try:
        desc = call_bedrock_for_text(prompt, max_tokens=50, temperature=temp).strip()
        if not desc:
            desc = call_bedrock_for_text(prompt, max_tokens=40, temperature=temp + 0.10).strip()
        return desc if len(desc) <= 80 else desc[:77] + "..."
    except Exception:
        return f"Generate strategic content for {state.get('campaign_objective', '').lower()}"

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
    if human_feedback:
        regen_attempt = state.get("regen_attempt_number", 1)
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post and ensure the new version is distinctly different."
    
    # Apply enhanced variation for regenerations
    regen_attempt = state.get("regen_attempt_number", 1)
    if regen_attempt > 1:
        base_content_prompt = enhance_prompt(base_content_prompt, state)
    
    # Get dynamic temperature
    temperature = get_dynamic_temperature(state)
    
    # Platform-specific max tokens
    max_tokens_map = {
        "email": 1200,
        "facebook": 1000,
        "whatsapp": 800,
        "x": 500,
        "sms": 300,
        "instagram": 1000
    }
    max_tokens = max_tokens_map.get(platform, 1000)
    
    try:
        content = call_bedrock_for_text(
            prompt=base_content_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
    except Exception as e:
        content = f"Error generating {platform} content: {str(e)}"
    
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

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """Supervisor agent that coordinates social media content generation."""
    return {
        "messages": ["Social media agents supervisor initialized"],
        "current_step": "social_media_agents_supervisor"
    }

# Platform-specific functions using the DRY generic function
def create_instagram_post(state: State) -> Dict[str, Any]:
    """Agent that creates professional Instagram posts using AWS Bedrock."""
    return create_social_media_post(state, "instagram")

def create_facebook_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic Facebook posts using AWS Bedrock."""
    return create_social_media_post(state, "facebook")

def create_x_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic X (Twitter) posts using AWS Bedrock."""
    return create_social_media_post(state, "x")

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic WhatsApp messages using AWS Bedrock."""
    return create_social_media_post(state, "whatsapp")

def create_email_post(state: State) -> Dict[str, Any]:
    """Agent that creates strategic email communications using AWS Bedrock."""
    return create_social_media_post(state, "email")

def create_sms_post(state: State) -> Dict[str, Any]:
    """Agent that creates SMS posts using AWS Bedrock."""
    return create_social_media_post(state, "sms")
