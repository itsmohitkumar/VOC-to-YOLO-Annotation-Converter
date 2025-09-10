from typing import Dict, Any
from langgraph.graph import StateGraph
from src.models import State

from src.campaign_agent.system_agents import (
    orchestrator_agent,
    system_agent_orchestrator,
    prompt_optimization,
    text_generator,
    content_reviewer,
    plan_generator,
    content_validator,
    web_search_tool,
    PLATFORM_AGENT_MAP
)

from src.agent.campaign_agent.social_media_agents import (
    social_media_agents_supervisor,
    create_instagram_post,
    create_facebook_post,
    create_x_post,
    create_whatsapp_post,
    create_email_post,
    create_sms_post
)
from complete_redesigned_db import bulk_create_campaign_content  # Import from redesigned DB

# ------------------------ BUILD GRAPH ------------------------
graph = StateGraph(State)

# ------------------------ SYSTEM AGENT NODES ------------------------
graph.add_node("orchestrator_agent", orchestrator_agent)
graph.add_node("system_agent_orchestrator", system_agent_orchestrator)

def web_search_agent(state: State) -> Dict[str, Any]:
    """Web search agent that uses the web search tool."""
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")

    search_query = f"{campaign_objective} {campaign_description} {target_audience} marketing campaign trends 2024"

    try:
        search_results = web_search_tool.invoke(search_query)
        return {
            "messages": [f"Web search completed for: {search_query[:100]}..."],
            "current_step": "web_search_agent",
            "search_results": search_results,
            "search_query": search_query
        }
    except Exception as e:
        return {
            "messages": [f"Web search failed: {str(e)}"],
            "current_step": "web_search_agent",
            "search_results": "No web search results available",
            "search_query": search_query
        }

graph.add_node("web_search_agent", web_search_agent)
graph.add_node("prompt_optimization", prompt_optimization)
graph.add_node("text_generator", text_generator)
# NOTE: image_generator node completely removed
graph.add_node("content_reviewer", content_reviewer)
graph.add_node("plan_generator", plan_generator)
graph.add_node("content_validator", content_validator)

# ------------------------ SOCIAL MEDIA AGENT NODES ------------------------
graph.add_node("social_media_agents_supervisor", social_media_agents_supervisor)
graph.add_node("create_instagram_post", create_instagram_post)
graph.add_node("create_facebook_post", create_facebook_post)
graph.add_node("create_x_post", create_x_post)
graph.add_node("create_whatsapp_post", create_whatsapp_post)
graph.add_node("create_email_post", create_email_post)
graph.add_node("create_sms_post", create_sms_post)

# ------------------------ ENTRY POINT ------------------------
graph.set_entry_point("orchestrator_agent")

# ------------------------ REGENERATION ROUTER ------------------------
def regeneration_router(state: State) -> str:
    if state.get("is_regeneration", False):
        print("🔄 Regeneration mode detected: Routing directly to social media agents supervisor")
        return "social_media_agents_supervisor"
    else:
        print("🔄 Normal mode: Proceeding to stage router")
        return stage_router(state)

graph.add_conditional_edges(
    "orchestrator_agent",
    regeneration_router,
    {
        "social_media_agents_supervisor": "social_media_agents_supervisor",
        "plan_generator": "plan_generator",
        "system_agent_orchestrator": "system_agent_orchestrator"
    }
)

# ------------------------ STAGE ROUTING ------------------------
def stage_router(state: State) -> str:
    current_stage = state.get("stage", "plan_generation")
    plan_approved = state.get("plan_approved", False)
    print(f"🔄 Stage Router: current_stage={current_stage}, plan_approved={plan_approved}")
    if current_stage == "plan_generation":
        print("📋 Routing to plan_generator for plan generation stage")
        return "plan_generator"
    elif current_stage == "content_generation" and plan_approved:
        print("📝 Routing to system_agent_orchestrator for content generation stage")
        return "system_agent_orchestrator"
    else:
        print("📋 Default routing to plan_generator")
        return "plan_generator"

# ------------------------ STAGE 1: PLAN GENERATION ------------------------
graph.add_edge("plan_generator", "__end__")

# ------------------------ STAGE 2: CONTENT GENERATION WORKFLOW ------------------------
graph.add_edge("system_agent_orchestrator", "web_search_agent")
graph.add_edge("web_search_agent", "prompt_optimization")
graph.add_edge("prompt_optimization", "text_generator")
# NOTE: Removed image_generator from flow - goes directly to content_reviewer
graph.add_edge("text_generator", "content_reviewer")
graph.add_edge("content_reviewer", "content_validator")

# ------------------------ PHASE 3: SOCIAL MEDIA AGENTS WORKFLOW ------------------------
graph.add_edge("content_validator", "social_media_agents_supervisor")

def social_media_router(state: State) -> str:
    current_post_id = state.get("current_post_id")
    if current_post_id:
        platform = current_post_id.split('_')[0].lower()
        if platform in PLATFORM_AGENT_MAP:
            print(f"🔄 Routing to {platform} agent for post_id: {current_post_id}")
            return f"create_{platform}_post"
        else:
            print(f"⚠️ Unknown platform in post_id: {current_post_id}")
            return "__end__"
    else:
        platforms = state.get("platforms", ["instagram"])
        if "instagram" in platforms:
            return "create_instagram_post"
        elif "facebook" in platforms:
            return "create_facebook_post"
        elif "x" in platforms:
            return "create_x_post"
        elif "whatsapp" in platforms:
            return "create_whatsapp_post"
        elif "email" in platforms:
            return "create_email_post"
        elif "sms" in platforms:
            return "create_sms_post"
        else:
            return "create_instagram_post"

graph.add_conditional_edges(
    "social_media_agents_supervisor",
    social_media_router,
    ["create_instagram_post", "create_facebook_post", "create_x_post",
     "create_whatsapp_post", "create_email_post", "create_sms_post"]
)

# In regeneration mode, end after platform agent
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()


from typing import Dict, Any, List
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from src.models import State
from src.vectorDB import hybrid_search
from src.llm.bedrock import call_bedrock_for_text
from .social_media_agents import (
    create_instagram_post, create_facebook_post, create_x_post,
    create_whatsapp_post, create_email_post, create_sms_post
)
from complete_redesigned_db import create_campaign_plan, bulk_create_campaign_content, log_audit, DatabaseError
from src.llm.prompts import DAILY_CONTENT_STRATEGY_PROMPT
import json
import logging

logger = logging.getLogger(__name__)

# Mapping from platform name to agent function
PLATFORM_AGENT_MAP = {
    "instagram": create_instagram_post,
    "facebook": create_facebook_post,
    "x": create_x_post,
    "whatsapp": create_whatsapp_post,
    "email": create_email_post,
    "sms": create_sms_post
}

def orchestrator_agent(state: State) -> Dict[str, Any]:
    """
    Main orchestrator agent with improved debugging for regeneration mode.
    """
    is_regen = state.get("is_regeneration", False)
    plan_approved = state.get("plan_approved", False)
    stage = state.get("stage", "plan_generation")
    current_post_id = state.get("current_post_id", "")
   
    print(f"🎭 Orchestrator Agent Debug:")
    print(f"   is_regeneration: {is_regen}")
    print(f"   plan_approved: {plan_approved}")
    print(f"   stage: {stage}")
    print(f"   current_post_id: {current_post_id}")
   
    if is_regen and current_post_id:
        return {
            "messages": [f"Orchestrator: Regeneration mode for {current_post_id}"],
            "current_step": "orchestrator_agent",
            "stage": "regeneration",
            "is_regeneration": True,
            "current_post_id": current_post_id
        }
    elif plan_approved and stage == "content_generation":
        return {
            "messages": ["Orchestrator: Starting content generation phase"],
            "current_step": "orchestrator_agent",
            "stage": "content_generation"
        }
    else:
        return {
            "messages": ["Orchestrator: Starting campaign plan generation"],
            "current_step": "orchestrator_agent",
            "stage": "plan_generation"
        }

def system_agent_orchestrator(state: State) -> Dict[str, Any]:
    """
    System agent orchestrator that manages system-level tasks.
    """
    return {
        "messages": ["System agent orchestrator initialized"],
        "current_step": "system_agent_orchestrator"
    }

def prompt_optimization(state: State) -> Dict[str, Any]:
    """
    Prompt optimization agent that optimizes prompts for content generation using vector database context.
    Uses hybrid search to retrieve relevant context directly from the vector database.
    """
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")
    target_audience_location = state.get("target_audience_location", "")
    collection_name = state.get("collection_name", "default_collection")
   
    # Base prompt elements
    base_prompt_elements = {
        "objective": campaign_objective,
        "description": campaign_description,
        "audience": target_audience,
        "audience_location": target_audience_location,
        "theme": state.get("campaign_theme"),
        "location": state.get("target_location", "Global")
    }
   
    # Enhanced prompt elements using vector database and web search context
    improved_prompt_elements = base_prompt_elements.copy()
   
    # Get web search results from state
    web_search_results = state.get("search_results", "")
   
    # Create search query from campaign parameters
    search_query = f"{campaign_objective} {campaign_description} {target_audience} campaign strategy content"

    try:
        # Use hybrid search to get relevant context
        search_result = hybrid_search(
            query=search_query,
            collection_name=collection_name,
            n_results=5
        )
       
        if search_result.get("success") and search_result.get("results"):
            context_results = search_result["results"]
            context_insights = [result["text"] for result in context_results if result.get("text")]
            context_sources = [result["metadata"].get("source", "unknown") for result in context_results]
           
            context_keywords = []
           
            # Analyze context insights for relevant keywords and themes
            for insight in context_insights[:5]:  # Use top 5 insights
                words = insight.lower().split()
                relevant_terms = [word for word in words if len(word) > 4 and
                                  any(keyword in word for keyword in ['campaign', 'brand', 'message', 'content', 'audience', 'strategy'])]
                context_keywords.extend(relevant_terms[:2])  # Limit keywords per insight
           
            # Remove duplicates and limit total keywords
            context_keywords = list(set(context_keywords))[:10]
           
            # Improve prompt elements with context
            if context_keywords:
                improved_prompt_elements["context_keywords"] = context_keywords
           
            if web_search_results:
                improved_prompt_elements["web_search_results"] = web_search_results
           
            if context_sources:
                improved_prompt_elements["reference_sources"] = list(set(context_sources))[:3]  # Top 3 unique sources
           
            # Create context-aware prompt guidance
            context_guidance = f"Incorporate insights from {len(context_insights)} relevant context sources and web search results"
            if context_keywords:
                context_guidance += f", focusing on themes related to: {', '.join(context_keywords[:5])}"
           
            improved_prompt_elements["context_guidance"] = context_guidance
            improved_prompt_elements["context_insights"] = context_insights[:3]  # Store top 3 insights
           
            messages = [
                "Prompt optimization completed with vector database and web search context integration",
                f"Improved prompts with {len(context_insights)} context insights from {len(set(context_sources))} sources and web search results",
                f"Extracted {len(context_keywords)} relevant keywords for content focus"
            ]
            context_improved = True
        else:
            # Fallback when no context is available
            improved_prompt_elements["context_guidance"] = "Using campaign parameters only - no relevant context found in vector database"
            if web_search_results:
                improved_prompt_elements["web_search_results"] = web_search_results
            messages = [
                "Prompt optimization completed using campaign parameters and web search results only",
                "No relevant context found in vector database - using standard optimization approach with web search"
            ]
            context_improved = False
           
    except Exception as e:
        # Handle any errors with hybrid search
        improved_prompt_elements["context_guidance"] = "Using campaign parameters only - error accessing vector database"
        messages = [
            "Prompt optimization completed using campaign parameters only",
            f"Error accessing vector database: {str(e)} - using standard optimization approach"
        ]
        context_improved = False
    
    # Generate daily strategy if we have platform and campaign info
    daily_strategy = None
    if state.get("platform") and state.get("campaign_objective"):
        try:
            strategy_prompt = DAILY_CONTENT_STRATEGY_PROMPT.format(
                current_day=state.get("current_day", 1),
                total_days=state.get("total_days", 7),
                campaign_theme=state.get("campaign_theme", ""),
                campaign_objective=state.get("campaign_objective", ""),
                target_audience=state.get("target_audience", ""),
                location=state.get("target_audience_location", ""),
                platform=state.get("platform", "")
            )
            
            daily_strategy = call_bedrock_for_text(
                prompt=strategy_prompt,
                max_tokens=300,
                temperature=0.7
            )
            
            # Add to enhanced prompt elements
            improved_prompt_elements["daily_strategy"] = daily_strategy
            messages.append("Daily content strategy generated")
            
        except Exception as e:
            logger.warning(f"Daily strategy generation failed: {e}")
    
    # Persist optimized prompts if campaign_id exists
    try:
        campaign_id = state.get("campaign_id")
        if campaign_id:
            log_audit("prompt_optimization", campaign_id, "UPDATE", "system", new_values=improved_prompt_elements)
    except DatabaseError as e:
        logger.error(f"Failed to log prompt optimization: {e}")
    
    return {
        "messages": messages,
        "current_step": "prompt_optimization",
        "optimized_prompts": improved_prompt_elements,
        "context_improved": context_improved
    }

def text_generator(state: State) -> Dict[str, Any]:
    """
    Text generation agent that creates text content.
    """
    optimized_prompts = state.get("optimized_prompts", {})
   
    # Create a detailed prompt for the LLM
    prompt = f"""Generate content based on the following:
   
    Objective: {optimized_prompts.get('objective')}
    Description: {optimized_prompts.get('description')}
    Audience: {optimized_prompts.get('audience')}
    Audience Location: {optimized_prompts.get('audience_location')}
    Theme: {optimized_prompts.get('theme')}
    Location: {optimized_prompts.get('location')}
    Context Guidance: {optimized_prompts.get('context_guidance')}
    Context Keywords: {', '.join(optimized_prompts.get('context_keywords', [])) if isinstance(optimized_prompts.get('context_keywords'), list) else optimized_prompts.get('context_keywords', '')}
    Web Search Results: {optimized_prompts.get('web_search_results')}
    """
   
    generated_text = call_bedrock_for_text(
        prompt=prompt,
        max_tokens=2000,
        temperature=0.7
    )
   
    return {
        "messages": ["Text generation completed using AWS Bedrock"],
        "current_step": "text_generator",
        "generated_text": generated_text
    }

def content_reviewer(state: State) -> Dict[str, Any]:
    """
    Content review agent that reviews generated content.
    """
    return {
        "messages": ["Content review completed"],
        "current_step": "content_reviewer"
    }

def content_formatter(state: State) -> Dict[str, Any]:
    """
    Content formatting agent that formats content for different platforms.
    """
    return {
        "messages": ["Content formatting completed"],
        "current_step": "content_formatter"
    }

def plan_generator(state: State) -> Dict[str, Any]:
    """
    Plan generator agent that creates the initial campaign plan structure.
    This runs in stage 1 to generate the basic plan outline for approval.
    """
    base_plan = state.get("base_plan_dict", {})
    platforms = state.get("platforms", ["instagram", "facebook", "x", "whatsapp", "email", "sms"])
   
    # Create correct structure - platform -> week -> day
    campaign_plan = {}
   
    for platform in platforms:
        campaign_plan[platform] = {}  # Each platform at root level
       
        for week_key, week_data in base_plan.items():
            # Use proper week naming (week_1, week_2, etc.)
            week_num = f"week_{week_key.split('_')[-1]}" if '_' in week_key else f"week_1"
            campaign_plan[platform][week_num] = {}
           
            for day_index, day_info in enumerate(week_data):
                day_key = f"Day_{day_index + 1}"
                agent_f = PLATFORM_AGENT_MAP.get(platform)
               
                if agent_f:
                    agent_state = state.copy()
                    agent_state["current_day"] = day_index + 1
                    agent_state["total_days"] = len(week_data)
                    # Ensure no image generation
                    agent_state["generate_images"] = False
                    agent_state["image_generation_enabled"] = False
                    try:
                        result = agent_f(agent_state)
                        post = result.get(f"{platform}_post")
                        task_description = post.get('task_description') if post else f"AI-generated content for {platform}"
                       
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
   
    # Persist plan to DB
    try:
        campaign_id = state.get("campaign_id")  # Assuming campaign_id in state
        plan_id = create_campaign_plan(campaign_id, campaign_plan, "system")
        log_audit("campaign_plans", plan_id, "INSERT", "system", new_values={"plan": campaign_plan})
    except DatabaseError as e:
        logger.error(f"Failed to persist plan: {e}")

    return {
        "messages": ["Campaign plan outline generated - awaiting approval"],
        "current_step": "plan_generator",
        "campaign_plan": campaign_plan,
        "stage": "plan_generation"
    }

def content_validator(state: State) -> Dict[str, Any]:
    """
    Content validation agent that generates full content after approval using AI agents.
    This runs in stage 2 to generate complete campaign content.
    """
    base_plan = state.get("base_plan_dict", {})
    platforms = state.get("platforms", ["instagram", "facebook", "x", "whatsapp", "email", "sms"])
    campaign_theme = state.get("campaign_theme")

    campaign_plan: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # Resolve platform agent map safely
    platform_agent_map = state.get("PLATFORM_AGENT_MAP")
    if not isinstance(platform_agent_map, dict):
        platform_agent_map = globals().get("PLATFORM_AGENT_MAP", {}) if isinstance(globals().get("PLATFORM_AGENT_MAP", {}), dict) else {}

    for platform in platforms:
        campaign_plan[platform] = {}

        for week_key, week_data in base_plan.items():
            week_num = f"week_{week_key.split('_')[-1]}" if isinstance(week_key, str) and "_" in week_key else "week_1"
            if week_num not in campaign_plan[platform]:
                campaign_plan[platform][week_num] = {}

            # Ensure week_data is iterable by days
            if isinstance(week_data, (list, tuple)):
                day_iter = list(enumerate(week_data, start=1))
            elif isinstance(week_data, dict):
                def _day_key(k: Any) -> Any:
                    try:
                        if isinstance(k, str) and k.lower().startswith("day_"):
                            return int(k.split("_")[-1])
                    except Exception:
                        pass
                    return k
                day_iter = [(k if isinstance(k, int) else k, v) for k, v in sorted(week_data.items(), key=lambda kv: _day_key(kv[0]))]
            else:
                day_iter = []

            for day_idx_or_key, day_info in day_iter:
                if isinstance(day_idx_or_key, int):
                    day_index = day_idx_or_key
                    day_key = f"Day_{day_index}"
                else:
                    day_key = str(day_idx_or_key)
                    try:
                        day_index = int(day_key.split("_")[-1])
                    except Exception:
                        day_index = 1

                agent_f = platform_agent_map.get(platform)
               
                if agent_f:
                    # Build agent state - no image generation
                    agent_state = dict(state)
                    agent_state.update({
                        "platform": platform,
                        "current_week": week_num,
                        "current_day": day_index,
                        "total_days": len(day_iter),
                        "day_info": day_info,
                        "campaign_theme": campaign_theme,
                        "generate_images": False,
                        "image_generation_enabled": False
                    })

                    try:
                        result = agent_f(agent_state) or {}
                        if not isinstance(result, dict):
                            result = {"result": result}

                        # Flexible extraction of post payload
                        post = (
                            result.get(f"{platform}_post")
                            or result.get("post")
                            or result.get("data")
                            or result
                        )

                        # Default task and content
                        task_description = f"AI-generated {platform} content for day {day_index}"
                        content_text = ""

                        if isinstance(post, dict):
                            content_text = str(post.get("content") or post.get("text") or post.get("body") or "")
                            task_description = str(post.get("task_description") or task_description)
                        else:
                            content_text = "" if post is None else str(post)

                        campaign_plan[platform][week_num][day_key] = {
                            "task": task_description,
                            "content": content_text,
                            # NOTE: No image-related fields
                            "human_feedback": "",
                            "regeneration_count": 0
                        }

                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"AI generation error for {platform}",
                            "content": f"Error generating content: {e}",
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No AI agent found for {platform}",
                        "content": f"Platform {platform} not supported",
                        "human_feedback": "",
                        "regeneration_count": 0
                    }

    # Persist generated content to DB
    try:
        campaign_id = state.get("campaign_id")  # Assuming in state
        bulk_create_campaign_content(campaign_id, campaign_plan, "system")
        log_audit("campaign_content", campaign_id, "BATCH_INSERT", "system", new_values={"plan": campaign_plan})
    except DatabaseError as e:
        logger.error(f"Failed to persist content: {e}")

    return {
        "messages": [f"AI-powered content generated for '{campaign_theme or 'campaign'}' using AWS Bedrock (no images)"],
        "current_step": "content_validator",
        "campaign_plan": campaign_plan
    }

@tool
def web_search_tool(query: str) -> str:
    """
    Web search tool for finding relevant information.
    
    Args:
        query: The search query
        
    Returns:
        Search results as a string
    """
    search = DuckDuckGoSearchRun()
    return search.run(query)


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
from src.llm.bedrock import call_bedrock_for_text
import time
import random
import json
from complete_redesigned_db import add_content_feedback, update_campaign_content, log_audit, DatabaseError

def log_generation_info(state: State, platform: str) -> None:
    """Log basic information about content generation."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
    feedback = state.get("human_feedback_text", "")
    attempt = state.get("regen_attempt_number", 0)
   
    print(f"🔍 {platform} agent:")
    print(f"   regeneration_mode: {is_regen}")
    print(f"   post_id: {post_id}")
    print(f"   attempt_number: {attempt}")
    print(f"   has_feedback: {bool(feedback)}")
    if feedback:
        print(f"   feedback_preview: {feedback[:50]}...")

def calculate_temperature(state: State) -> float:
    """Calculate generation temperature based on feedback and attempt number."""
    strength = state.get("feedback_strength", "medium")
    attempt = state.get("regen_attempt_number", 1)
    base_temps = {"light": 0.75, "medium": 0.80, "strong": 0.85}
    base_temp = base_temps.get(strength, 0.80)
   
    if attempt == 1:
        return base_temp
    elif attempt == 2:
        return min(base_temp + 0.15, 0.95)
    else:  # 3rd+ attempt
        return min(base_temp + 0.25, 1.0)

def add_variation_instructions(prompt: str, state: State) -> str:
    """Add variation instructions for content regeneration."""
    attempt = state.get("regen_attempt_number", 1)
    lines = [
        f"--- REGENERATION ATTEMPT {attempt} (MUST BE DIFFERENT) ---"
    ]
   
    strength = state.get("feedback_strength", "medium")
    if strength == "strong":
        lines.append("IMPORTANT: Completely rewrite with new structure and approach.")
    elif strength == "medium":
        lines.append("IMPORTANT: Substantially change content and messaging.")
    else:
        lines.append("IMPORTANT: Improve content with fresh ideas.")
   
    if state.get("previous_variants"):
        prev_count = len(state['previous_variants'])
        lines.append(f"AVOID similarity to the last {prev_count} versions.")
   
    if state.get("force_variation", False):
        lines.append("VARIATION REQUIRED: Output must differ in style and tone.")
   
    # Add uniqueness seed
    uniqueness_seed = f"Generation seed: {time.time()} | Focus: {random.choice(['creative', 'innovative', 'fresh', 'bold'])}"
    lines.append(uniqueness_seed)
   
    return prompt + "\n\n" + "\n".join(lines)

def create_task_description(state: State, phase: str, day_context: str) -> str:
    """Generate task description for the content."""
    prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=state.get("campaign_objective", ""),
        target_audience=state.get("target_audience", ""),
        target_audience_location=state.get("target_audience_location", ""),
        phase=phase,
        day_context=day_context
    )
   
    temp = calculate_temperature(state) * 0.90
    try:
        desc = call_bedrock_for_text(prompt, max_tokens=50, temperature=temp).strip()
        if not desc:
            desc = call_bedrock_for_text(prompt, max_tokens=40, temperature=temp + 0.10).strip()
        return desc if len(desc) <= 80 else desc[:77] + "..."
    except Exception:
        return f"Generate content for {state.get('campaign_objective', '').lower()}"

def is_content_different(new_content: str, previous_variants: list) -> bool:
    """Check if new content is sufficiently different from previous versions."""
    if not previous_variants:
        return True
    new_words = set(new_content.lower().split())
    for variant in previous_variants:
        prev_words = set(variant.get("content", "").lower().split())
        overlap = len(new_words.intersection(prev_words)) / max(len(new_words), len(prev_words), 1)
        if overlap > 0.7:
            return False
    return True

def create_social_media_post(state: State, platform: str) -> Dict[str, Any]:
    """Create social media post content for specified platform."""
   
    # Log generation info
    log_generation_info(state, platform)
   
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
        1: "This is the opening content piece",
        2: "This is the follow-up content piece",
        3: "This builds momentum from previous content"
    }
    day_context = day_context_map.get(current_day, f"This continues the {phase} phase")
   
    # Create task description
    task_description = create_task_description(state, phase, day_context)
   
    # Build content prompt
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
    regen_attempt = state.get("regen_attempt_number", 1)
   
    if human_feedback:
        base_content_prompt += f"\n\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\n"
        base_content_prompt += "IMPORTANT: Incorporate this feedback and make the content different from the previous version."
        # Persist feedback to DB
        try:
            content_id = state.get("content_id")
            if content_id:
                add_content_feedback(content_id, human_feedback, state.get("feedback_strength", "medium"), regen_attempt)
                log_audit("content_feedback", content_id, "INSERT", "system", new_values={"feedback_text": human_feedback})
        except DatabaseError as e:
            logger.error(f"Failed to persist feedback: {e}")
   
    # Apply variation instructions for regenerations
    if regen_attempt > 1:
        base_content_prompt = add_variation_instructions(base_content_prompt, state)
        print(f"🔄 Added variation instructions for attempt {regen_attempt}")
   
    # Get temperature
    temperature = calculate_temperature(state)
    print(f"🌡️ Using temperature: {temperature} for attempt {regen_attempt}")
   
    # Platform-specific token limits
    max_tokens_map = {
        "instagram": 1000,
        "facebook": 1000,
        "x": 500,
        "whatsapp": 800,
        "email": 1200,
        "sms": 300
    }
    max_tokens = max_tokens_map.get(platform, 1000)
   
    # Generate content with variation checking
    previous_variants = state.get("previous_variants", [])
    content = ""
   
    for retry in range(3):  # Retry up to 3 times if too similar
        try:
            print(f"🎯 Generating content for {platform} (retry {retry})")
            content = call_bedrock_for_text(
                prompt=base_content_prompt,
                max_tokens=max_tokens,
                temperature=temperature + (retry * 0.05)
            )
           
            if content and content.strip():
                if is_content_different(content, previous_variants):
                    print(f"Content variation check passed for {platform}")
                    break
                else:
                    print(f"Content too similar, retrying {platform} generation")
            else:
                print(f"Empty content generated for {platform}, retrying")
               
        except Exception as e:
            print(f"Error generating {platform} content (retry {retry}): {str(e)}")
            content = f"Error generating {platform} content: {str(e)}"
            break
    else:
        content += " [NOTE: Retry limit reached; content may be similar]"
        print(f"⚠️ Retry limit reached for {platform}")
   
    # Build post response
    post_key = f"{platform}_post"
    post = {
        "task_description": task_description,
        "content": content,
        "generation_info": {
            "attempt": regen_attempt,
            "temperature_used": temperature,
            "feedback_incorporated": bool(human_feedback),
            "feedback_strength": state.get("feedback_strength", "medium"),
            "seed": state.get("random_seed", ""),
            "generation_timestamp": time.time()
        }
    }
   
    print(f"📄 Generated {platform} content (length: {len(content)})")
    if regen_attempt > 1:
        print(f"🔄 Regeneration complete for {platform}: attempt {regen_attempt}")
   
    # Update content in DB if content_id exists
    try:
        content_id = state.get("content_id")
        if content_id:
            update_campaign_content(content_id, "system", content_text=content, regeneration_count=regen_attempt)
            log_audit("campaign_content", content_id, "UPDATE", "system", new_values={"content": content})
    except DatabaseError as e:
        logger.error(f"Failed to update content in DB: {e}")
   
    return {
        post_key: post,
        "messages": [f"{platform} post for day {current_day} (attempt {regen_attempt}) created with temp {temperature:.2f}"],
        "current_step": f"create_{platform}_post",
        "content": content,
        "task_description": task_description
    }

def social_media_agents_supervisor(state: State) -> Dict[str, Any]:
    """Coordinate social media content generation."""
    is_regen = state.get("is_regeneration", False)
    post_id = state.get("current_post_id", "")
   
    print(f"🎭 Social Media Supervisor:")
    print(f"   regeneration_mode: {is_regen}")
    print(f"   current_post_id: {post_id}")
   
    return {
        "messages": ["Social media supervisor initialized"],
        "current_step": "social_media_agents_supervisor"
    }

# Platform-specific functions
def create_instagram_post(state: State) -> Dict[str, Any]:
    """Create Instagram post content."""
    return create_social_media_post(state, "instagram")

def create_facebook_post(state: State) -> Dict[str, Any]:
    """Create Facebook post content."""
    return create_social_media_post(state, "facebook")

def create_x_post(state: State) -> Dict[str, Any]:
    """Create X (Twitter) post content."""
    return create_social_media_post(state, "x")

def create_whatsapp_post(state: State) -> Dict[str, Any]:
    """Create WhatsApp message content."""
    return create_social_media_post(state, "whatsapp")

def create_email_post(state: State) -> Dict[str, Any]:
    """Create email content."""
    return create_social_media_post(state, "email")

def create_sms_post(state: State) -> Dict[str, Any]:
    """Create SMS content."""
    return create_social_media_post(state, "sms")



from fastapi import APIRouter, HTTPException, Form
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from complete_redesigned_db import (get_user_by_username, get_campaign_by_name, update_campaign_status,
                                    create_campaign_plan, approve_campaign_plan, get_latest_campaign_plan,
                                    add_content_feedback, get_content_by_post_id, get_campaign_platform_names,
                                    bulk_create_campaign_content, log_audit, DatabaseError, ValidationError)
from utils.logger import logger
import json
import copy
from datetime import datetime
from .excel_utils import generate_and_upload_combined_excel_to_s3  # Assuming this exists
import re

router = APIRouter()

ALLOWED_PLATFORMS = ["instagram", "facebook", "x", "whatsapp", "email", "sms"]  # Define allowed platforms

class CampaignPlanResponse(BaseModel):
    campaign_name: str
    success: bool
    campaign_plan: Dict
    platforms: List[str]
    uploaded_images: List
    generated_images: List
    total_images: int
    content_review_status: str
    message: str
    image_generation_status: str
    target_audience_location: str

class FeedbackItem(BaseModel):
    post_id: str
    feedback_text: str

class MultiFeedbackRequest(BaseModel):
    feedbacks: List[FeedbackItem]

@router.post("/{username}/{campaign_name}/approve", response_model=CampaignPlanResponse)
async def approve_campaign_plan(
    username: str,
    campaign_name: str
):
    """
    Approve a campaign plan and generate full content (no images),
    loading the existing plan directly from the database.
    """
    try:
        logger.info(f"Approving campaign plan for user: {username}, campaign: {campaign_name}")

        # Validate user
        user = get_user_by_username(username)
        if not user:
            raise HTTPException(404, f"User '{username}' not found")

        # Validate campaign exists
        campaign = get_campaign_by_name(username, campaign_name)
        if not campaign:
            raise HTTPException(404, f"Campaign '{campaign_name}' not found for user '{username}'")

        campaign_id = campaign["campaign_id"]

        # Fetch stored plan from new DB
        stored_plan = get_latest_campaign_plan(campaign_id)
        if not stored_plan:
            raise HTTPException(404, f"No existing plan found for '{username}/{campaign_name}'")

        # Parse plan_data
        stored = stored_plan["plan_data"]
        if not isinstance(stored, dict):
            raise HTTPException(500, "Invalid plan data format")

        # Validate required fields
        required = ["campaign_name", "campaign_objective", "campaign_description",
                    "start_date", "end_date", "target_audience", "platforms", "campaign_plan"]
        missing = [f for f in required if f not in stored]
        if missing:
            raise HTTPException(400, f"Stored plan missing: {missing}")

        # Normalize audience_info
        tai = stored.get("target_audience_info", [])
        if isinstance(tai, str):
            try:
                tai = json.loads(tai)
            except:
                tai = [e.strip() for e in tai.split(",") if e.strip()]

        # Date validation
        date_info = calculate_date_info(stored["start_date"], stored["end_date"])  # Assuming this function exists
        if "error" in date_info:
            raise HTTPException(400, date_info["error"])

        # Validate platforms
        platforms = [p for p in stored.get("platforms", []) if p in ALLOWED_PLATFORMS]
        if not platforms:
            raise HTTPException(400, "No valid platforms in stored plan")

        # Retrieve the plan dict
        campaign_plan = stored["campaign_plan"]
        if isinstance(campaign_plan, str):
            campaign_plan = json.loads(campaign_plan)

        # Build approval state
        approval_state = State(
            campaign_id=campaign_id,  # Add campaign_id to state
            campaign_name=stored["campaign_name"],
            campaign_objective=stored["campaign_objective"],
            campaign_description=stored["campaign_description"],
            start_date=stored["start_date"],
            end_date=stored["end_date"],
            target_audience=stored["target_audience"],
            target_audience_info=tai,
            target_audience_location=stored.get("target_audience_location",""),
            base_plan_dict=copy.deepcopy(date_info["week_mapping"]),
            platforms=platforms,
            stage="content_generation",
            plan_approved=True,
            generate_images=False,
            max_regen_attempts=3,
            current_regen_attempts={},
            campaign_plan=campaign_plan,
            messages=[],
            current_step="approval"
        )

        # Generate full content
        final_state = await system_agents.ainvoke(approval_state)
        state_dict = dict(final_state)
        full_plan = state_dict.get("campaign_plan")
        if not full_plan:
            raise HTTPException(404, "Content generation failed after approval")

        # Sanitize images field
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: (sanitize(v) if k.lower() not in
                             ("images","image_base64","image_s3_key") else [])
                        for k,v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(i) for i in obj]
            return obj

        full_plan = sanitize(full_plan)

        # Upload Excel
        excel_url = generate_and_upload_combined_excel_to_s3(full_plan, f"{username}/{campaign_name}", S3_BUCKET)
        if not excel_url:
            raise HTTPException(500, "Excel upload failed")

        # Store approve_response in DB
        approve_data = {
            **stored,
            "campaign_plan": full_plan,
            "current_step": state_dict.get("current_step","completed"),
            "messages": state_dict.get("messages",[]),
            "stage":"content_generation",
            "plan_approved":True,
            "excel_s3_url":excel_url,
            "content_review_status":"approved"
        }
        update_campaign_status(campaign_id, "approved", "system")
        approve_campaign_plan(stored_plan["plan_id"], "system", "Approved via API")

        # Log audit
        log_audit("campaigns", campaign_id, "UPDATE", "system", old_values={"status": "planning"}, new_values={"status": "approved"})

        return CampaignPlanResponse(
            campaign_name=stored["campaign_name"],
            success=True,
            campaign_plan=full_plan,
            platforms=platforms,
            uploaded_images=[],
            generated_images=[],
            total_images=0,
            content_review_status="approved",
            message=f"Campaign approved. Excel: {excel_url}",
            image_generation_status="skipped",
            target_audience_location=stored.get("target_audience_location","")
        )

    except (DatabaseError, ValidationError) as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving campaign plan: {e}")
        raise HTTPException(500, "Error approving campaign plan")

@router.post("/{username}/{campaign_name}/feedback") 
async def submit_feedback(     
    username: str,     
    campaign_name: str,     
    feedback_request: MultiFeedbackRequest 
) -> Dict[str, Any]:     
    """     
    Feedback batch regeneration (DB-backed):     
    - Reads stored plan / feedback from DB (agentic_campaign_planner) instead of S3 JSON.     
    - Produces versioned approved_plan_v{batch_version} and updates DB with feedback_response.     
    """     
    try:         
        campaign_full_name = f"{username}/{campaign_name}"         
        logger.info(f"Processing enhanced multi-feedback for {campaign_full_name}")         
          
        # Validations         
        user_data = get_user_by_username(username)         
        if not user_data:             
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")         
          
        campaign = get_campaign_by_name(username, campaign_name)
        if not campaign:             
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found for user '{username}'")         
          
        if not feedback_request or not feedback_request.feedbacks:             
            raise HTTPException(status_code=400, detail="feedbacks list is required and cannot be empty")         
          
        # Deduplicate feedbacks         
        deduped_feedbacks = []         
        seen_post_ids_lower = set()         
        original_post_ids = []         
        for fb in feedback_request.feedbacks:             
            pid = (fb.post_id or "").strip()             
            if not pid or not isinstance(pid, str):                 
                raise HTTPException(status_code=400, detail="Each feedback item must include a non-empty post_id")             
            pid_lower = pid.lower()             
            if pid_lower in seen_post_ids_lower:                 
                logger.info(f"Skipping duplicate post_id in request: {pid}")                 
                continue             
            seen_post_ids_lower.add(pid_lower)             
            deduped_feedbacks.append(fb)             
            original_post_ids.append(pid)         
        if not deduped_feedbacks:             
            raise HTTPException(status_code=400, detail="No valid, unique post_ids provided in feedbacks")         
          
        # --- Load plans and stored state from DB ---         
        stored_plan_full = None         
        campaign_plan = None         
        planner_record = get_latest_campaign_plan(campaign["campaign_id"])         
        if not planner_record:             
            raise HTTPException(status_code=404, detail=f"No planner record found for '{campaign_full_name}'")         
          
        # Parse plan_data         
        stored_plan_full = planner_record["plan_data"]         
        campaign_plan = stored_plan_full.get("campaign_plan")         
        if not campaign_plan:             
            raise HTTPException(status_code=404, detail=f"Campaign plan not found for '{campaign_full_name}'")         
          
        if isinstance(campaign_plan, str):             
            try:                 
                campaign_plan = json.loads(campaign_plan)             
            except json.JSONDecodeError:                 
                logger.warning("Stored campaign_plan is a string but not valid JSON; proceeding with original value")         
          
        # --- Load feedback tracking from DB or init default ---         
        feedback_dict = {}         
        fb_raw = planner_record.get("feedback_response")         
        if fb_raw:             
            try:                 
                feedback_dict = fb_raw if isinstance(fb_raw, dict) else json.loads(fb_raw)             
            except Exception as e:                 
                logger.warning(f"Could not parse feedback_response JSON from DB for {campaign_full_name}: {e}")                 
                feedback_dict = {}         
        if not feedback_dict:             
            feedback_dict = {                 
                "campaign_name": campaign_full_name,                 
                "feedback_history": [],                 
                "current_regen_attempts": {},                 
                "max_regen_attempts": 3,                 
                "approved_plan_versions": [],                 
                "previous_variants": {}             
            }         
          
        # Normalize attempt keys         
        current_attempts_dict = feedback_dict.get("current_regen_attempts", {}) or {}         
        normalized_attempts = {}         
        for k, v in current_attempts_dict.items():             
            if isinstance(k, str):                 
                kl = k.strip().lower()                 
                normalized_attempts[kl] = max(v, normalized_attempts.get(kl, 0))         
        feedback_dict["current_regen_attempts"] = normalized_attempts         
        feedback_dict.setdefault("previous_variants", {})         
          
        # --- Load state from DB or fallback ---         
        state_dict = {}         
        plan_raw = planner_record.get("plan_data")         
        if plan_raw:             
            try:                 
                state_dict = plan_raw if isinstance(plan_raw, dict) else json.loads(plan_raw)             
            except Exception as e:                 
                logger.warning(f"Could not parse plan_data JSON from DB for {campaign_full_name}: {e}")                 
                state_dict = {}         
        if not state_dict:             
            state_dict = {                 
                "campaign_name": campaign_full_name,                 
                "campaign_plan": campaign_plan,                 
                "current_regen_attempts": feedback_dict.get("current_regen_attempts", {}),                 
                "max_regen_attempts": feedback_dict.get("max_regen_attempts", 3),                 
                "is_regen_required": True             
            }         
          
        full_plan = copy.deepcopy(campaign_plan)         
        details: Dict[str, Any] = {}         
        human_feedback_map: Dict[str, str] = {}         
          
        # --- Pre-check all posts for max attempts to reject batch if any exceed ---         
        current_regen_attempts = feedback_dict.get("current_regen_attempts", {})         
        max_regen_attempts = feedback_dict.get("max_regen_attempts", 3)         
        for fb in deduped_feedbacks:             
            pid_norm = fb.post_id.lower()             
            current_attempts = current_regen_attempts.get(pid_norm, 0)             
            if current_attempts >= max_regen_attempts:                 
                raise HTTPException(status_code=400, detail=f"Max regeneration attempts reached for post_id '{fb.post_id}'")         
          
        # --- helper functions (kept same) ---         
        def classify_feedback_strength(feedback_text: str) -> str:             
            feedback_lower = feedback_text.lower()             
            strong_indicators = ["completely rewrite", "totally different", "start over", "completely change"]             
            medium_indicators = ["improve", "enhance", "better", "more", "add", "include"]             
            if any(indicator in feedback_lower for indicator in strong_indicators):                 
                return "strong"             
            elif any(indicator in feedback_lower for indicator in medium_indicators):                 
                return "medium"             
            else:                 
                return "light"         
          
        def get_progressive_temperature(attempt_number: int, feedback_strength: str) -> float:             
            base_temps = {"light": 0.8, "medium": 0.85, "strong": 0.9}             
            base_temp = base_temps.get(feedback_strength, 0.8)             
            if attempt_number == 1:                 
                return base_temp             
            elif attempt_number == 2:                 
                return min(base_temp + 0.1, 0.95)             
            else:                 
                return 0.95         
          
        def generate_enhanced_seed(post_id: str, attempt_number: int, feedback_text: str) -> str:             
            timestamp = datetime.utcnow().isoformat()             
            seed_input = f"{post_id}|{attempt_number}|{feedback_text[:50]}|{timestamp}"             
            return hashlib.sha256(seed_input.encode()).hexdigest()         
          
        def content_similarity_check(new_content: str, previous_variants: List[Dict]) -> bool:             
            if not previous_variants or not new_content:                 
                return True             
            new_words = set(new_content.lower().split())             
            for variant in previous_variants[-2:]:                 
                prev_content = variant.get("content", "")                 
                if prev_content:                     
                    prev_words = set(prev_content.lower().split())                     
                    similarity = len(new_words.intersection(prev_words)) / max(len(new_words), len(prev_words), 1)                     
                    if similarity > 0.7:                         
                        return False             
            return True         
          
        version_number = 0         
        processed_post_ids: List[str] = []         
          
        # --- Main feedback loop ---         
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
              
            # Process successful regeneration / merge             
            if isinstance(new_day_node, dict):                 
                merged_node = copy.deepcopy(new_day_node)             
            else:                 
                existing = full_plan[platform_key][week_key].get(day_key, {})                 
                merged_node = {}                 
                if isinstance(existing, dict):                     
                    merged_node.update(existing)                 
                fallback_keys = (                     
                    "task", "content", "caption", "headline", "cta",                     
                    "hook", "angle", "hashtags", "title", "body", "notes"                 
                )                 
                for k in fallback_keys:                     
                    if k in final_state_dict:                         
                        merged_node[k] = final_state_dict[k]             
              
            # Clean up any image-related fields (kept)             
            image_related_keys = ["image_path_s3", "image_paths", "image_urls", "images", "image_prompt"]             
            for img_key in image_related_keys:                 
                if img_key in merged_node:                     
                    merged_node[img_key] = []             
            merged_node["human_feedback"] = fb_text             
            merged_node["regenration_count"] = version_number             
            merged_node["feedback_strength"] = feedback_strength             
            merged_node["temperature_used"] = temperature             
            full_plan[platform_key][week_key][day_key] = merged_node             
              
            # Store variant for future similarity checking             
            pv_map = feedback_dict.setdefault("previous_variants", {})             
            pv_list = pv_map.get(pid_norm, [])             
            variant_snapshot = {                 
                k: merged_node.get(k)                 
                for k in ("content", "caption", "headline", "cta", "hook", "angle", "hashtags", "title", "body", "notes")                 
                if k in merged_node             
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
          
        # --- Generate Final Plan object ---         
        processed_count = len([k for k, v in details.items() if v.get("success")])         
        all_attempts = feedback_dict.get("current_regen_attempts", {}) or {}         
          
        # NEW: Incremental batch_version based on existing DB versions         
        status = get_campaign_status(username, campaign_name)         
        existing_versions = sum([             
            status["has_approved_plan_v1"],             
            status["has_approved_plan_v2"],             
            status["has_approved_plan_v3"]         
        ])         
        batch_version = existing_versions + 1         
          
        if batch_version > 3:             
            raise HTTPException(status_code=400, detail="Maximum feedback versions (3) reached for this campaign")         
          
        approved_plan_data = {             
            "campaign_name": campaign_full_name,             
            "campaign_plan": full_plan,             
            "current_step": "completed",             
            "messages": [],             
            "stage": "content_generation",             
            "plan_approved": True,             
            "generated_images": [],  # Empty             
            "image_generation_status": "disabled",             
            "generated_at": datetime.utcnow().isoformat(),             
            "human_feedback_map": human_feedback_map.copy(),             
            "batch_version": batch_version         
        }         
          
        # Add metadata from stored plan (state_dict first, then stored_plan_full, then defaults)         
        meta_defaults = {             
            "campaign_objective": "",             
            "campaign_description": "",             
            "start_date": "",             
            "end_date": "",             
            "target_audience": "",             
            "target_audience_info": [],             
            "target_audience_location": "",             
            "platforms": []         
        }         
        for mk, dv in meta_defaults.items():             
            val = state_dict.get(mk) if state_dict.get(mk) is not None else (stored_plan_full.get(mk) if stored_plan_full and isinstance(stored_plan_full, dict) else dv)             
            approved_plan_data[mk] = val         
          
        # Generate and upload Excel to S3 ONLY         
        excel_s3_url = ""         
        try:             
            excel_s3_url = generate_and_upload_combined_excel_to_s3(                 
                campaign_plan=approved_plan_data["campaign_plan"],                 
                campaign_name=campaign_full_name,                 
                bucket=S3_BUCKET,                 
                plan_data=approved_plan_data,                 
                version=batch_version             
            )             
            logger.info(f"Successfully uploaded Excel v{batch_version}: {excel_s3_url}")         
        except Exception as e:             
            logger.error(f"Failed generate/upload excel for batch v{batch_version}: {e}")         
          
        approved_plan_data["excel_s3_url"] = excel_s3_url         
          
        # Update feedback tracking in database (append to approved_plan_versions)         
        feedback_dict.setdefault("approved_plan_versions", []).append({             
            "version": batch_version,             
            "excel_s3_url": excel_s3_url,             
            "post_ids": list(original_post_ids),             
            "timestamp": datetime.utcnow().isoformat(),             
            "processed_count": processed_count         
        })         
          
        # Build response         
        response = {             
            "campaign_name": campaign_full_name,             
            "success": True,             
            "message": f"Enhanced feedback processing completed for {processed_count} of {len(deduped_feedbacks)} posts with progressive temperature control.",             
            "campaign_plan": approved_plan_data["campaign_plan"],             
            "platforms": approved_plan_data.get("platforms", []),             
            "generated_images": [],  # empty             
            "image_generation_status": "disabled",             
            "excel_s3_url": excel_s3_url,             
            "processed": len(deduped_feedbacks),             
            "batch_version": batch_version,             
            "timestamp": datetime.utcnow().isoformat(),             
            "details": details,             
            "enhancement_features": {                 
                "progressive_temperature": True,                 
                "content_similarity_checking": True,                 
                "feedback_strength_classification": True,                 
                "enhanced_seed_generation": True             
            }         
        }         
          
        # Update database with enhanced feedback response         
        try:             
            total_regenerations = sum(all_attempts.values())  # Cumulative across posts             
            fields_to_update = {                 
                "feedback_response": json.dumps({                     
                    "feedback": feedback_dict,                     
                    "approved_plan": approved_plan_data,                     
                    "details": details,                     
                    "enhancements": response["enhancement_features"]                 
                }, ensure_ascii=False),                 
                "regeneration_count": total_regenerations  # Updated to cumulative             
            }             
              
            # store the whole response into approved_plan_v{n} if v1..v3             
            if batch_version in {1, 2, 3}:                 
                fields_to_update[f"approved_plan_v{batch_version}"] = json.dumps(response, ensure_ascii=False)               
              
            affected = update_campaign_plan(                 
                campaign_id=campaign["campaign_id"],                 
                **fields_to_update             
            )             
            if affected == 0:                 
                raise ValueError("Database update failed - no rows affected")             
            logger.info(f"Successfully updated database for {campaign_full_name} v{batch_version}")         
        except Exception as e:             
            logger.error(f"Failed DB update for {campaign_full_name}: {e}")             
            raise HTTPException(status_code=500, detail="Failed to persist feedback state")         
          
        return response       
      
    except HTTPException:         
        raise     
    except Exception as e:         
        logger.error(f"Unexpected error in enhanced submit_feedback: {e}")         
        raise HTTPException(status_code=500, detail="Error processing feedback: Contact support team!")



from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import HttpUrl
from complete_redesigned_db import (create_campaign, add_campaign_asset, get_user_by_username, get_campaign_by_name,
                                    get_user_campaigns, delete_campaign, get_campaign_status, get_latest_campaign_plan,
                                    log_audit, DatabaseError, ValidationError)
from src.storage.s3 import upload_file
from src.llm.bedrock import generate_summary
from typing import Optional
from src.webscraper import async_scrape_url, clean_data
from src.vectorDB import add_web_scraping_data,delete_collection
from src.campaign.file_processor import process_campaign_file
from src.models import CampaignRegistrationResponse, DeleteCollectionResponse, CampaignListResponse, CampaignInfo
from utils.env_vars import *
from utils.logger import logger
import boto3

# Set up S3
s3_client = boto3.client('s3', region_name=AWS_REGION)

# Create API router
router = APIRouter(
    prefix="/campaign",
    tags=["2.*Campaign Registration*"],
    responses={404: {"description": "Not found"}},
)

@router.post("/register/{username}", response_model=CampaignRegistrationResponse)
async def register_campaign(
    username: str,
    campaign_name: str = Form(...),
    location: str = Form(...),
    web_link: Optional[HttpUrl] = Form(None),
    supporting_web_link: Optional[HttpUrl] = Form(None),
    campaign_voice: Optional[UploadFile] = File(None),
    campaign_book: Optional[UploadFile] = File(None),
    logo: Optional[UploadFile] = File(None)
    ):
    """
    Register a new campaign for a user.
    - **username**: Username of the user registering the campaign
    - **campaign_name**: Name of the campaign (unique per user)
    - **location**: Location of the campaign
    - **web_link**: URL to scrape for campaign information
    - **supporting_web_link**: Alternative URL to scrape
    - **campaign_voice**: Description of the campaign's tone/purpose
    - **campaign_book**: Optional PDF/TXT file with campaign guidelines
    - **logo**: Optional image file for the campaign
    Returns the processing result with URLs to uploaded files.
    """
    try:
        logger.info(f"Authenticating user with username: {username}")
        # Convert campaign name to lowercase
        campaign_name = campaign_name.strip().lower()
        logger.info(f"Processing campaign registration for: {campaign_name}")
        # Validate if campaign name already exists
        existing_campaign = get_campaign_by_name(username, campaign_name)
        if existing_campaign:
            logger.error(f"Campaign name '{campaign_name}' already exists.")
            raise HTTPException(status_code=400, detail=f"Campaign name '{campaign_name}' already exists.")
        campaign_name = campaign_name.strip()
        logger.info(f"Processing campaign registration for: {campaign_name}")
        # Initialize response
        response = {
            "username": username,
            "campaign_name": campaign_name,
            "success": False,
            "message": "Processing campaign registration",
            "web_link_scraped": False,
            "supporting_web_link_scraped": False,
            "vector_db_entries": 0
        }
        # Prepare data for database entry
        campaign_voice_filename = campaign_voice.filename if campaign_voice else None
        campaign_book_filename = campaign_book.filename if campaign_book else None
        logo_filename = logo.filename if logo else None
        # Save request data to the database using the provided function
        try:
            campaign_id = create_campaign(
                user_id=user["user_id"],
                campaign_name=campaign_name,
                location=location,
                created_by=username
            )
            log_audit("campaigns", campaign_id, "INSERT", username)
            logger.info(f"Campaign registration data saved to the database for user: {username}")
        except (DatabaseError, ValidationError) as e:
            logger.error(f"Error saving campaign registration data to the database: {e}")
            raise HTTPException(status_code=500, detail=f"Error saving campaign registration data to the database: {str(e)}")
        # Process campaign voice if provided
        campaign_voice_result = None
        if campaign_voice:
            logger.info(f"Processing campaign voice: {campaign_voice.filename}")
            documents_folder = f"campaigns/{username}/{campaign_name}/documents"
            campaign_voice_result = process_campaign_file(
                campaign_voice,
                AWS_AGENTIC_BUCKET,
                s3_client,
                "campaign_voice",
                folder=documents_folder
            )
            if campaign_voice_result["success"]:
                add_campaign_asset(
                    campaign_id=campaign_id,
                    asset_type="campaign_voice",
                    asset_name=campaign_voice_filename,
                    asset_url=campaign_voice_result.get("url"),
                    file_path=campaign_voice_result.get("path"),
                    file_size_bytes=campaign_voice_result.get("size"),
                    mime_type=campaign_voice.content_type
                )
                logger.info(f"Campaign voice processed successfully: {campaign_voice.filename}")
            else:
                logger.error(f"Error processing campaign voice: {campaign_voice_result['message']}")
        # Process campaign book if provided
        campaign_book_result = None
        if campaign_book:
            logger.info(f"Processing campaign book: {campaign_book.filename}")
            documents_folder = f"campaigns/{username}/{campaign_name}/documents"
            campaign_book_result = process_campaign_file(
                campaign_book,
                AWS_AGENTIC_BUCKET,
                s3_client,
                "campaign_book",
                folder=documents_folder
            )
            if campaign_book_result["success"]:
                add_campaign_asset(
                    campaign_id=campaign_id,
                    asset_type="campaign_book",
                    asset_name=campaign_book_filename,
                    asset_url=campaign_book_result.get("url"),
                    file_path=campaign_book_result.get("path"),
                    file_size_bytes=campaign_book_result.get("size"),
                    mime_type=campaign_book.content_type
                )
                logger.info(f"Campaign book processed successfully: {campaign_book.filename}")
            else:
                logger.error(f"Error processing campaign book: {campaign_book_result['message']}")
        # Process logo if provided
        logo_result = None
        if logo:
            logger.info(f"Processing logo: {logo.filename}")
            images_folder = f"campaigns/{username}/{campaign_name}/logo"
            logo_result = process_campaign_file(
                logo,
                AWS_AGENTIC_BUCKET,
                s3_client,
                "logo",
                folder=images_folder
            )
            if logo_result["success"]:
                add_campaign_asset(
                    campaign_id=campaign_id,
                    asset_type="logo",
                    asset_name=logo_filename,
                    asset_url=logo_result.get("url"),
                    file_path=logo_result.get("path"),
                    file_size_bytes=logo_result.get("size"),
                    mime_type=logo.content_type
                )
                logger.info(f"Logo processed successfully: {logo.filename}")
            else:
                logger.error(f"Error processing logo: {logo_result['message']}")
        # Scrape web link
        web_link_data = None
        if web_link:
            try:
                logger.info(f"Scraping web link: {web_link}")
                html = await async_scrape_url(str(web_link))
                if html:
                    web_link_data = clean_data(str(web_link), html)
                    response["web_link_scraped"] = True
                    logger.info(f"Web link scraped successfully: {web_link}")
                else:
                    logger.error(f"Error scraping web link: {web_link}")
            except Exception as e:
                logger.error(f"Error scraping web link {web_link}: {e}")
        # Scrape supporting web link
        supporting_web_link_data = None
        if supporting_web_link:
            try:
                logger.info(f"Scraping supporting web link: {supporting_web_link}")
                html = await async_scrape_url(str(supporting_web_link))
                if html:
                    supporting_web_link_data = clean_data(str(supporting_web_link), html)
                    response["supporting_web_link_scraped"] = True
                    logger.info(f"Supporting web link scraped successfully: {supporting_web_link}")
                else:
                    logger.error(f"Error scraping supporting web link: {supporting_web_link}")
            except Exception as e:
                logger.error(f"Error scraping supporting web link {supporting_web_link}: {e}")
        # Save web data to Markdown file
        web_data_md = ""
        if web_link_data:
            web_data_md += f"Web Link: {web_link}\nText: {web_link_data.get('text', '')}\n\n"
        if supporting_web_link_data:
            web_data_md += f"Supporting Web Link: {supporting_web_link}\nText: {supporting_web_link_data.get('text', '')}\n\n"
        if web_data_md:
            upload_file(
                web_data_md.encode('utf-8'),
                AWS_AGENTIC_BUCKET,
                s3_client,
                "web_data.md",
                folder=f"campaigns/{username}/{campaign_name}/documents"
            )
            logger.info(f"Web data saved to S3: campaigns/{username}/{campaign_name}/generated_contents/web_data.md")
        # Combine all text data
        combined_text = f"Campaign Name: {campaign_name}\nLocation: {location}\n\n"
        if campaign_voice_result and campaign_voice_result.get("extracted_text"):
            combined_text += f"Campaign Voice:\n{campaign_voice_result['extracted_text']}\n\n"
        if campaign_book_result and campaign_book_result.get("extracted_text"):
            combined_text += f"Campaign Book:\n{campaign_book_result['extracted_text']}\n\n"
        if logo_result and logo_result.get("extracted_text"):
            combined_text += f"Logo Text:\n{logo_result['extracted_text']}\n\n"
        # Add web link data if available
        if web_link_data:
            combined_text += f"Web Link Content:\nTitle: {web_link_data.get('title', '')}\n"
            combined_text += f"Description: {web_link_data.get('description', '')}\n"
            combined_text += f"Text: {web_link_data.get('text', '')}\n\n"
        if supporting_web_link_data:
            combined_text += f"Supporting Web Link Content:\nTitle: {supporting_web_link_data.get('title', '')}\n"
            combined_text += f"Description: {supporting_web_link_data.get('description', '')}\n"
            combined_text += f"Text: {supporting_web_link_data.get('text', '')}\n\n"
        # Invoke Bedrock model to generate summary
        summary_text = generate_summary(combined_text)
        # Save summary to S3
        summary_file_content = f"Summary:\n{summary_text}\n"
        summary_file_path = f"summary.md"
        upload_file(
            summary_file_content.encode('utf-8'),
            AWS_AGENTIC_BUCKET,
            s3_client,
            summary_file_path,
            folder=f"campaigns/{username}/{campaign_name}/generated_contents"
        )
        # Create metadata
        metadata = {
            "username": username,
            "campaign_name": campaign_name,
            "location": location,
            "campaign_voice": campaign_voice_filename if campaign_voice else "",
            "web_link": str(web_link),
            "supporting_web_link": str(supporting_web_link),
            "campaign_book": campaign_book_filename if campaign_book else "",
            "logo": logo_filename if logo else "",
            "type": "campaign"
        }
        # Add to vector database
        vector_db_data = {
            "url": f"campaign:{campaign_name}",
            "title": f"Campaign: {campaign_name}",
            "description": f"Location: {location}, Voice: {campaign_voice}",
            "text": combined_text,
            "metadata": metadata
        }
        try:
            vector_db_result = add_web_scraping_data(f"{username}/{campaign_name}", vector_db_data, AWS_AGENTIC_BUCKET, s3_client)
            if vector_db_result.get("success", False):
                response["vector_db_entries"] = vector_db_result.get("chunks_added", 0)
                logger.info(f"Campaign data stored in vector DB: {vector_db_result.get('message')}")
            else:
                logger.error(f"Error storing campaign data in vector DB: {vector_db_result['message']}")
        except Exception as e:
            logger.error(f"Error storing campaign data in vector DB: {e}")
        response["success"] = True
        response["message"] = "Campaign registered successfully"
        return response
    except Exception as e:
        logger.error(f"Error processing campaign registration: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing campaign registration: {str(e)}")
   
@router.delete("/delete/{username}", response_model=DeleteCollectionResponse)
async def delete_campaign_data(
    username: str,
    campaign_name: str
):
    """
    Delete a campaign from the vector database and database.
    Parameters:
    - username: The username of the user requesting the deletion.
    - campaign_name: The name of the campaign to delete.
    This will delete the campaign after validating the user and ownership.
    """
    try:
        # Convert campaign_name to lowercase
        campaign_name = campaign_name.lower()
        logger.info(f"Authenticating user with username: {username}")
        # Validate username against the database
        user_data = get_user_by_username(username)
        if not user_data:
            logger.error(f"User with username '{username}' not found.")
            raise HTTPException(status_code=404, detail=f"User with username '{username}' not found.")
        logger.info(f"User authenticated successfully. Username: {username}")
        # Check if the campaign exists and belongs to the user
        campaign = get_campaign_by_name(campaign_name, username)
        if not campaign:
            logger.error(f"Campaign '{campaign_name}' not found for user '{username}'.")
            raise HTTPException(status_code=404, detail=f"Campaign '{campaign_name}' not found or you do not have permission to delete it.")
        # Proceed with deletion from vector database
        try:
            result = delete_collection(
                AWS_AGENTIC_BUCKET,
                collection_name=campaign_name,
                username=username  # Pass username to delete_collection
            )
        except TypeError as e:
            logger.error(f"Error deleting collection: {e}")
            raise HTTPException(status_code=500, detail=f"Error deleting collection: {str(e)}")
        # Delete campaign from database
        try:
            delete_campaign(username, campaign_name, username)
            logger.info(f"Campaign '{campaign_name}' deleted from database for username: {username}")
        except Exception as e:
            logger.error(f"Error deleting campaign from database: {e}")
            raise HTTPException(status_code=500, detail=f"Error deleting campaign from database: {str(e)}")
        return {
            "success": result.get("success", False),
            "message": result.get("message", "Campaign deletion process completed"),
            "collection_name": campaign_name
        }
    except Exception as e:
        logger.error(f"Error deleting campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting campaign: {str(e)}")

@router.get("/list/{username}", response_model=CampaignListResponse)
async def list_user_campaigns(username: str):
    """
    List all campaigns for a user.
    """
    try:
        logger.info(f"Authenticating user with username: {username}")
        campaigns = get_user_campaigns(username)

        if not campaigns:
            logger.info(f"No campaigns found for username: {username}")
            return {
                "username": username,
                "campaigns": [],
                "success": True,
                "message": "No campaigns found for this user",
            }

        campaign_list = []

        for c in campaigns:
            status = get_campaign_status(username, c["campaign_name"])

            plan_exists = fetch_plan_exists(username, c["campaign_name"])

            campaign_item = CampaignInfo(
                campaign_name=c["campaign_name"],
                location=c.get("location"),
                web_link=c.get("web_link"),
                supporting_web_link=c.get("supporting_web_link"),
                campaign_voice=c.get("campaign_voice"),
                campaign_book=c.get("campaign_book"),
                logo=c.get("logo"),
                created_by=c.get("created_by"),
                created_at=c.get("created_at"),
                approved_plan=status["approved_plan"],
                regeneration_count=status["regeneration_count"],
                plan_response=plan_exists,   # embed boolean here
            )
            campaign_list.append(campaign_item)

        return {
            "username": username,
            "campaigns": campaign_list,
            "success": True,
            "message": f"Found {len(campaign_list)} campaigns for user",
        }
    except ValueError as ve:
        logger.error(f"User with username '{username}' not found: {ve}")
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error listing campaigns for user {username}: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing campaigns: {str(e)}")



import json
from typing import List, Dict
from fastapi import APIRouter, HTTPException
from complete_redesigned_db import get_campaign_by_name, get_latest_campaign_plan, get_campaign_media
from src.storage.s3 import list_files, get_s3_file_content
from utils.logger import logger
from utils.env_vars import *

# Create API router
router = APIRouter(
    prefix="/dashboard",
    tags=["3.*Dashboard Management*"]
)

@router.get("/{username}/list-files", response_model=List[Dict[str, str]])
async def list_s3_files(username: str, campaign_name: str):
    """
    Endpoint to list files in a specific campaign folder in S3 for a given user.

    Parameters:
    - username (str): Username of the user.
    - campaign_name (str): Name of the campaign folder inside "campaigns/".

    Returns:
    - List of files with metadata.
    """
    try:
        # Convert campaign_name to lowercase
        campaign_name = campaign_name.lower()

        # Construct the folder path by appending the campaign name to "campaigns/<username>/"
        folder = f"campaigns/{username}/{campaign_name}"

        # Retrieve files from the specified folder in S3
        files = list_files(folder)
        return files
    except Exception as e:
        logger.error(f"Failed to list files for user '{username}' in campaign '{campaign_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list files for user '{username}' in campaign '{campaign_name}': {str(e)}")

@router.get("/{username}/{campaign_name}/responses", response_model=dict)
async def get_campaign_responses(username: str, campaign_name: str):
    responses = fetch_campaign_responses(username, campaign_name)
    if not responses:
        raise HTTPException(404, "Campaign not found.")

    json_fields = [
        "plan_response", "approve_response", "feedback_response",
        "approved_plan_v1", "approved_plan_v2", "approved_plan_v3"
    ]
    for key in json_fields:
        if key in responses and isinstance(responses[key], str):
            try:
                responses[key] = json.loads(responses[key])
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {key}")
                raise HTTPException(500, f"Invalid JSON in {key}")

    images = list_campaign_images(username, campaign_name)
    images_by_post = {}
    for img in images:
        pid = img["post_id"]
        images_by_post.setdefault(pid, []).append(img["image_base64"])
    logger.debug(f"Images map: {images_by_post}")

    def inject(plan_obj: dict):
        cp = plan_obj.get("campaign_plan", {})
        for platform, weeks in cp.items():
            for wk, days in weeks.items():
                for dy, post in days.items():
                    key = f"{platform}_{wk}_{dy}".lower()
                    post["images"] = images_by_post.get(key, [])

    for key in json_fields:
        val = responses.get(key)
        if isinstance(val, dict) and "campaign_plan" in val:
            inject(val)

    return responses
                       
@router.get("/{username}/view-summary/{campaign_name}")
async def view_summary(username: str, campaign_name: str):
    """
    Endpoint to fetch the text content of 'summary.md' from 'campaigns/<username>/<campaign_name>/generated_contents/summary.md' in S3.
    """
    try:
        # Convert campaign_name to lowercase
        campaign_name = campaign_name.lower()

        # Construct the full S3 key for summary.md
        file_key = f"campaigns/{username}/{campaign_name}/generated_contents/summary.md"
       
        # Use helper function to fetch content
        content = await get_s3_file_content(AWS_AGENTIC_BUCKET, file_key)
       
        return {"content": content}
    except Exception as e:
        logger.error(f"Failed to fetch summary for user '{username}' in campaign '{campaign_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary for user '{username}' in campaign '{campaign_name}': {str(e)}")



@router.post("/{username}/create/{campaign_name}", response_model=CampaignPlanResponse)
async def create_campaign_plan(
    username: str,
    campaign_name: str,
    campaign_objective: str = Form(...),
    campaign_description: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    target_audience: str = Form(...),
    target_audience_info: Optional[str] = Form(None),
    target_audience_location: str = Form(...),
    marketing_channels: List[str] = Form(default=["instagram", "facebook", "email", "whatsapp", "sms"])
):
    """
    Create a campaign plan with customizable marketing channels.
    """
    try:
        logger.info(f"Starting request validation for user: {username}, campaign: {campaign_name}")

        # ========================= Input validations =========================

        # Normalize and validate marketing channels
        processed_channels: List[str] = []
        if marketing_channels:
            for channel in marketing_channels:
                # Split on commas
                if isinstance(channel, str):
                    split_channels = [c.strip().lower() for c in channel.split(',') if c.strip()]
                    processed_channels.extend(split_channels)
                else:
                    processed_channels.append(str(channel).strip().lower())

        unique_marketing_channels = list(set(processed_channels))
        if not unique_marketing_channels:
            raise HTTPException(status_code=400, detail="At least one marketing channel must be selected")

        invalid_channels = [channel for channel in unique_marketing_channels if channel not in ALLOWED_PLATFORMS]
        if invalid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid marketing channels: {invalid_channels}. Allowed channels: {ALLOWED_PLATFORMS}"
            )
        logger.info(f"Validated marketing channels: {unique_marketing_channels}")

        # Validate dates
        date_info = calculate_date_info(start_date, end_date)
        if "error" in date_info:
            raise HTTPException(status_code=400, detail=date_info["error"])
        logger.info("Validated dates successfully")

        # Validate and parse target_audience_info
        audience_emails: List[str] = []
        if target_audience_info:
            processed_audience_info = target_audience_info.strip()
            if processed_audience_info:
                audience_emails = [
                    email.strip().strip('"').strip("'")
                    for email in processed_audience_info.split(",")
                    if email.strip()
                ]
                email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
                for email in audience_emails:
                    if not email_pattern.match(email):
                        raise HTTPException(status_code=400, detail=f"Invalid email format: {email}")
                logger.info(f"Validated {len(audience_emails)} email addresses")
            else:
                logger.info("target_audience_info was provided but empty → skipping email validation")
        else:
            logger.info("No target_audience_info provided → skipping email validation")

        # Validate user and campaign existence
        user = get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail=f"User with username '{username}' not found.")
        user_campaigns = get_user_campaigns(username)
        campaign_full_name = f"{username}/{campaign_name}"
        if campaign_name in [c["campaign_name"] for c in user_campaigns]:
            raise HTTPException(status_code=400, detail=f"Campaign '{campaign_name}' already exists for user '{username}'.")

        # Create campaign in new DB
        campaign_id = create_campaign(
            user_id=user["user_id"],
            campaign_name=campaign_name,
            campaign_objective=campaign_objective,
            campaign_description=campaign_description,
            location=target_audience_location,
            start_date=start_date,
            end_date=end_date,
            target_audience=target_audience,
            target_audience_location=target_audience_location,
            created_by=username
        )
        # Add platforms
        for channel in unique_marketing_channels:
            add_campaign_platform(campaign_id, channel)

        # ======================================== Retrieve context from vector database ========================================
        logger.info(f"Retrieving context from vector database for campaign: {campaign_full_name}")
        vector_context: List[Dict[str, Any]] = []
        try:
            search_queries = [
                f"{campaign_objective} {target_audience}",
                f"{campaign_description}",
                f"campaign planning {target_audience}"
            ]
            collection_name = campaign_full_name
            collection_info = get_collection_info(collection_name, user_id=user.get('user_id'))
            if collection_info.get('success') and collection_info.get('metadata', {}).get('count', 0) > 0:
                logger.info(f"Found vector database collection for user: {collection_name}")
                for query in search_queries:
                    search_results = hybrid_search(
                        query=query,
                        collection_name=collection_name,
                        n_results=3,
                        filter_expr=None
                    )
                    if search_results.get('success') and search_results.get('results'):
                        for result in search_results['results']:
                            if result.get('text'):
                                vector_context.append({
                                    'text': result['text'],
                                    'source': result.get('metadata', {}).get('source', 'unknown'),
                                    'score': result.get('score', 0),
                                    'query': query
                                })
                logger.info(f"Retrieved {len(vector_context)} context documents from vector database")
            else:
                logger.warning(f"No knowledge base found for user: {collection_name}. Falling back to web search and defaults.")
        except Exception as e:
            logger.error(f"Error retrieving context from vector database: {e}")
            # Continue instead of raising exception

        # Handle empty context gracefully
        if not vector_context:
            logger.warning(f"No relevant context retrieved for campaign: {campaign_full_name}. Proceeding with fallback context.")
            # Optional: Add default or web-search-based context here
            vector_context = [{
                'text': 'Default campaign planning insights: Focus on audience engagement and objective alignment.',
                'source': 'Fallback',
                'score': 1.0,
                'query': 'default'
            }]

        # ================================ Agentic workflow and generation ================================
        initial_state = State(
            campaign_id=campaign_id,  # Add campaign_id to state
            campaign_name=campaign_full_name,
            campaign_objective=campaign_objective,
            campaign_description=campaign_description,
            start_date=start_date,
            end_date=end_date,
            target_audience=target_audience,
            target_audience_location=target_audience_location,
            target_audience_info=audience_emails,
            base_plan_dict=copy.deepcopy(date_info["week_mapping"]),
            max_regen_attempts=3,
            current_regen_attempts={},
            platforms=unique_marketing_channels,
            generate_images=False,  # Images removed
            stage="plan_generation",
            plan_approved=False
        )

        final_state = await system_agents.ainvoke(initial_state)
        state_dict = dict(final_state)
        campaign_plan = state_dict.get("campaign_plan")

        if not campaign_plan:
            logger.error(f"No campaign plan generated. Final state keys: {list(state_dict.keys())}")
            raise HTTPException(status_code=404, detail="Campaign generation failed - no campaign plan generated!")

        # Ensure campaign_plan is a dict
        if isinstance(campaign_plan, str):
            try:
                campaign_plan = json.loads(campaign_plan)
            except json.JSONDecodeError:
                logger.warning("campaign_plan is a string but not valid JSON; returning as-is")
        elif hasattr(campaign_plan, "dict") and callable(getattr(campaign_plan, "dict")):
            campaign_plan = campaign_plan.dict()

        generated_images: List[Dict[str, Any]] = []
        image_generation_status = "skipped"
        content_review_status = "skipped"

        # Content review logic
        try:
            logger.info("Starting content review and validation")
            content_review_status, _ = content_review_service.review_campaign_content(
                campaign_plan,
                {
                    "campaign_objective": campaign_objective,
                    "campaign_description": campaign_description,
                    "target_audience": target_audience,
                    "target_audience_location": target_audience_location
                },
                unique_marketing_channels
            )
            logger.info(f"Content review completed. Status: {content_review_status}")
        except Exception as e:
            logger.error(f"Error in content review process: {e}")
            content_review_status = "error"

        # Upload Excel to S3
        try:
            bucket_name = S3_BUCKET
            excel_content = generate_campaign_excel(campaign_plan, campaign_full_name, stage="plan")
            excel_filename = f"{username}_{campaign_name}_plan.xlsx"
            s3_key = f"campaigns/{username}/{campaign_name}/campaign_planner/excel/{excel_filename}"
            excel_s3_url = upload_excel_to_s3(excel_content, s3_key, bucket_name)
            if not excel_s3_url:
                raise HTTPException(500, "Failed to upload Excel file to S3")
            logger.info(f"Excel uploaded: {excel_s3_url}")
        except Exception as e:
            logger.error(f"Excel upload failed: {e}")
            raise HTTPException(500, "Excel upload to S3 failed")

        # Prepare and store plan.json
        plan_data = {
            "campaign_name": campaign_full_name,
            "campaign_plan": campaign_plan,  # dict
            "current_step": state_dict.get("current_step", "completed"),
            "messages": state_dict.get("messages", []),
            "campaign_objective": campaign_objective,
            "campaign_description": campaign_description,
            "start_date": start_date,
            "end_date": end_date,
            "target_audience": target_audience,
            "target_audience_location": target_audience_location,
            "target_audience_info": audience_emails,
            "platforms": unique_marketing_channels,
            "generated_images": generated_images,
            "image_generation_status": image_generation_status,
            "content_review_status": content_review_status,
            "excel_s3_url": excel_s3_url
        }

        # Persist to DB
        plan_id = create_campaign_plan(campaign_id, plan_data, username)
        log_audit("campaign_plans", plan_id, "INSERT", username, new_values=plan_data)

        return CampaignPlanResponse(
            campaign_name=campaign_full_name,
            success=True,
            campaign_plan=campaign_plan,
            platforms=unique_marketing_channels,
            uploaded_images=[],
            generated_images=[],
            total_images=0,
            content_review_status=content_review_status,
            message=f"Campaign plan created. Excel: {excel_s3_url}",
            image_generation_status="skipped",
            target_audience_location=target_audience_location
        )

    except (DatabaseError, ValidationError) as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating campaign plan: {e}")
        raise HTTPException(500, "Error creating campaign plan")





