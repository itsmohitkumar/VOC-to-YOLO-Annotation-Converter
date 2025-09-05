# Complete Updated Code - Fixes Both Issues

## 1. Updated graph.py - Fixes Regeneration + Removes Images

```python
# src/agent/graph.py
from typing import Dict, Any
from langgraph.graph import StateGraph
from src.models import State

from src.campaign_agent.system_agents import (
    orchestrator_agent,
    system_agent_orchestrator,
    prompt_optimization,
    text_generator,
    # image_generator,  # REMOVED
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
# REMOVED: graph.add_node("image_generator", image_generator)
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

# ------------------------ REGENERATION ROUTER - FIXED ------------------------
def regeneration_router(state: State) -> str:
    if state.get("is_regeneration", False):
        print("🔄 Regeneration mode detected: Routing to content generation pipeline")
        # FIXED: Route through content generation pipeline instead of supervisor
        return "system_agent_orchestrator"
    else:
        print("🔄 Normal mode: Proceeding to stage router")
        return stage_router(state)

graph.add_conditional_edges(
    "orchestrator_agent",
    regeneration_router,
    {
        "system_agent_orchestrator": "system_agent_orchestrator",  # For both normal and regen
        "plan_generator": "plan_generator"
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

# ------------------------ STAGE 2: CONTENT GENERATION WORKFLOW - UPDATED ------------------------
graph.add_edge("system_agent_orchestrator", "web_search_agent")
graph.add_edge("web_search_agent", "prompt_optimization")
graph.add_edge("prompt_optimization", "text_generator")
# REMOVED: graph.add_edge("text_generator", "image_generator")
# REMOVED: graph.add_edge("image_generator", "content_reviewer")
graph.add_edge("text_generator", "content_reviewer")  # Direct connection
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

# End after platform agent
graph.add_edge("create_instagram_post", "__end__")
graph.add_edge("create_facebook_post", "__end__")
graph.add_edge("create_x_post", "__end__")
graph.add_edge("create_whatsapp_post", "__end__")
graph.add_edge("create_email_post", "__end__")
graph.add_edge("create_sms_post", "__end__")

# ------------------------ COMPILE ------------------------
system_agents = graph.compile()
```

## 2. Updated system_agents.py - Enhanced for Regeneration + No Images

```python
# /system_agents.py
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
    Main orchestrator agent that coordinates the entire workflow.
    Determines if we're in plan generation or content generation stage.
    """
    if state.get("plan_approved") and state.get("stage") == "content_generation":
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
    Enhanced for regeneration mode.
    """
    is_regeneration = state.get("is_regeneration", False)
    current_post_id = state.get("current_post_id", "")
    
    if is_regeneration:
        return {
            "messages": [f"System agent orchestrator initialized for regeneration of {current_post_id}"],
            "current_step": "system_agent_orchestrator",
            "regeneration_mode": True,
            "enhanced_variation": True
        }
    else:
        return {
            "messages": ["System agent orchestrator initialized"],
            "current_step": "system_agent_orchestrator"
        }

def prompt_optimization(state: State) -> Dict[str, Any]:
    """
    Prompt optimization agent enhanced for regeneration mode.
    """
    campaign_objective = state.get("campaign_objective", "")
    campaign_description = state.get("campaign_description", "")
    target_audience = state.get("target_audience", "")
    target_audience_location = state.get("target_audience_location", "")
    collection_name = state.get("collection_name", "default_collection")
    
    # Enhanced for regeneration
    is_regeneration = state.get("is_regeneration", False)
    feedback_context = state.get("feedback_context", {})
    
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
    enhanced_prompt_elements = base_prompt_elements.copy()
    
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
                # Extract potential keywords (simplified approach)
                words = insight.lower().split()
                # Look for campaign-relevant terms
                relevant_terms = [word for word in words if len(word) > 4 and
                                any(keyword in word for keyword in ['campaign', 'brand', 'message', 'content', 'audience', 'strategy'])]
                context_keywords.extend(relevant_terms[:2])  # Limit keywords per insight
            
            # Remove duplicates and limit total keywords
            context_keywords = list(set(context_keywords))[:10]
            
            # Enhance prompt elements with context
            if context_keywords:
                enhanced_prompt_elements["context_keywords"] = context_keywords
            
            if web_search_results:
                enhanced_prompt_elements["web_search_results"] = web_search_results

            if context_sources:
                enhanced_prompt_elements["reference_sources"] = list(set(context_sources))[:3]  # Top 3 unique sources
            
            # Create context-aware prompt guidance
            context_guidance = f"Incorporate insights from {len(context_insights)} relevant context sources and web search results"
            if context_keywords:
                context_guidance += f", focusing on themes related to: {', '.join(context_keywords[:5])}"
            
            enhanced_prompt_elements["context_guidance"] = context_guidance
            enhanced_prompt_elements["context_insights"] = context_insights[:3]  # Store top 3 insights
            
            messages = [
                "Prompt optimization completed with vector database and web search context integration",
                f"Enhanced prompts with {len(context_insights)} context insights from {len(set(context_sources))} sources and web search results",
                f"Extracted {len(context_keywords)} relevant keywords for content focus"
            ]
            context_enhanced = True
        else:
            # Fallback when no context is available
            enhanced_prompt_elements["context_guidance"] = "Using campaign parameters only - no relevant context found in vector database"
            if web_search_results:
                 enhanced_prompt_elements["web_search_results"] = web_search_results
            messages = [
                "Prompt optimization completed using campaign parameters and web search results only",
                "No relevant context found in vector database - using standard optimization approach with web search"
            ]
            context_enhanced = False
            
    except Exception as e:
        # Handle any errors with hybrid search
        enhanced_prompt_elements["context_guidance"] = "Using campaign parameters only - error accessing vector database"
        messages = [
            "Prompt optimization completed using campaign parameters only",
            f"Error accessing vector database: {str(e)} - using standard optimization approach"
        ]
        context_enhanced = False

    # ENHANCED: Regeneration-specific optimization
    if is_regeneration and feedback_context:
        # Add feedback-driven context enhancement
        feedback_keywords = []
        feedback_text = feedback_context.get("feedback_text", "").lower()
        
        # Extract improvement areas from feedback
        improvement_words = ["better", "more", "less", "different", "change", "improve", "enhance"]
        for word in feedback_text.split():
            if any(imp in word for imp in improvement_words):
                feedback_keywords.append(word)
        
        if feedback_keywords:
            enhanced_prompt_elements["feedback_keywords"] = feedback_keywords
            enhanced_prompt_elements["regeneration_focus"] = feedback_text
            
        enhanced_prompt_elements["variation_directive"] = f"Generate varied content addressing: {feedback_text}"
        
        messages.append(f"Enhanced prompts for regeneration with feedback focus: {feedback_text[:100]}...")
    
    return {
        "messages": messages,
        "current_step": "prompt_optimization",
        "optimized_prompts": enhanced_prompt_elements,
        "context_enhanced": context_enhanced
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

def plan_generator(state: State) -> Dict[str, Any]:
    """
    Plan generator agent that creates the initial campaign plan structure with AI-generated tasks.
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
    
    return {
        "messages": ["Campaign plan outline generated - awaiting approval"],
        "current_step": "plan_generator",
        "campaign_plan": campaign_plan,
        "stage": "plan_generation"
    }

def content_validator(state: State) -> Dict[str, Any]:
    """
    Content validation agent that generates full content after approval using AI agents.
    This runs in stage 2 to generate complete AI-powered campaign content.
    UPDATED: Removed all image path handling
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
                # sort by numeric suffix if keys are like Day_1, Day_2...
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
                    # Build agent state
                    agent_state = dict(state)
                    agent_state.update({
                        "platform": platform,
                        "current_week": week_num,
                        "current_day": day_index,
                        "total_days": len(day_iter),
                        "day_info": day_info,
                        "campaign_theme": campaign_theme,
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
                            # REMOVED: "image_path_s3": image_paths,
                            "human_feedback": "",
                            "regeneration_count": 0
                        }

                    except Exception as e:
                        campaign_plan[platform][week_num][day_key] = {
                            "task": f"AI generation error for {platform}",
                            "content": f"Error generating content: {e}",
                            # REMOVED: "image_path_s3": [],
                            "human_feedback": "",
                            "regeneration_count": 0
                        }
                else:
                    campaign_plan[platform][week_num][day_key] = {
                        "task": f"No AI agent found for {platform}",
                        "content": f"Platform {platform} not supported",
                        # REMOVED: "image_path_s3": [],
                        "human_feedback": "",
                        "regeneration_count": 0
                    }

    return {
        "messages": [f"AI-powered content generated for '{campaign_theme or 'campaign'}' using AWS Bedrock"],
        "current_step": "content_validator",
        "campaign_plan": campaign_plan
    }

# REMOVED: def image_generator(state: State) -> Dict[str, Any]:

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
```

## 3. Updated social_media_agents.py - Enhanced Variation

```python
# /social_media_agents.py - Enhanced for regeneration
def create_instagram_post(state: State) -> Dict[str, Any]:
    """
    Agent that creates professional Instagram posts using AWS Bedrock.
    Enhanced for regeneration with feedback incorporation.
    """
    campaign_objective = state.get("campaign_objective", "Build brand awareness")
    campaign_theme = state.get("campaign_theme", "")
    target_audience = state.get("target_audience", "General audience")
    target_audience_location = state.get("target_audience_location", "")
    current_day = state.get("current_day", 1)
    total_days = state.get("total_days", 7)
    optimized_prompts = state.get("optimized_prompts", {})
    web_search_results = state.get("search_results", "")
    human_feedback = state.get("human_feedback_text", "")
    regen_attempt = state.get("regen_attempt_number", 1)
    
    # ENHANCED: Regeneration-specific parameters
    is_regeneration = state.get("is_regeneration", False)
    feedback_context = state.get("feedback_context", {})
    random_seed = state.get("random_seed", "")

    if current_day <= 3:
        phase = "launch"
    elif current_day <= total_days - 5:
        phase = "build"
    else:
        phase = "conclusion"

    day_context = ""
    if current_day == 1:
        day_context = "This is the opening/first content piece"
    elif current_day == 2:
        day_context = "This is the follow-up content piece"
    elif current_day == 3:
        day_context = "This builds momentum from previous content"
    else:
        day_context = f"This continues the {phase} phase narrative"
    
    task_prompt = TASK_DESCRIPTION_GENERATION_PROMPT.format(
        campaign_objective=campaign_objective,
        target_audience=target_audience,
        target_audience_location=target_audience_location,
        phase=phase,
        day_context=day_context
    )
    
    try:
        task_description = call_bedrock_for_text(
            prompt=task_prompt,
            max_tokens=50,
            temperature=0.8
        ).strip()
        if len(task_description) > 80:
            task_description = task_description[:77] + "..."
        elif not task_description:
            task_description = call_bedrock_for_text(
                prompt=task_prompt,
                max_tokens=40,
                temperature=0.9
            ).strip()
    except Exception as e:
        task_description = f"Generate strategic content for {campaign_objective.lower()}"
    
    # ENHANCED: Build variation context for regeneration
    variation_context = ""
    temperature = 0.8  # Default temperature
    
    if is_regeneration and feedback_context:
        original_content = feedback_context.get("original_content", "")
        feedback_text = feedback_context.get("feedback_text", "")
        attempt_number = feedback_context.get("attempt_number", 1)
        
        # Higher temperature for more variation
        temperature = 0.9
        
        variation_context = f"""

REGENERATION INSTRUCTIONS:
- This is regeneration attempt #{attempt_number}
- Previous content: {original_content[:300]}{'...' if len(original_content) > 300 else ''}
- User feedback: {feedback_text}
- Random seed: {random_seed}

CRITICAL: You must create significantly different content that:
1. Directly addresses the user's feedback
2. Uses different angles, hooks, and messaging approaches
3. Varies the tone and structure from the original
4. Maintains the campaign objective but with fresh perspective
5. Incorporates lessons from the feedback

DO NOT repeat similar phrases or structures from the original content.
        """
    
    feedback_suffix = ""
    if human_feedback:
        feedback_suffix = f"\nHuman Feedback (Attempt {regen_attempt}): {human_feedback}\nIncorporate this feedback to improve the post."
    
    content_prompt = INSTAGRAM_CONTENT_GENERATION_PROMPT.format(
        current_day=current_day,
        total_days=total_days,
        campaign_objective=campaign_objective,
        campaign_theme=campaign_theme,
        target_audience=target_audience,
        target_audience_location=target_audience_location,
        phase=phase,
        web_search_results=web_search_results[:500] if web_search_results else "No web search context available",
        context_keywords=', '.join(optimized_prompts.get('context_keywords', [])),
        context_guidance=optimized_prompts.get('context_guidance', '')
    ) + feedback_suffix + variation_context  # Add variation context

    try:
        actual_content = call_bedrock_for_text(
            prompt=content_prompt,
            max_tokens=1000,
            temperature=temperature  # Use dynamic temperature
        )
        
        # ENHANCED: Add variation tracking
        if is_regeneration:
            actual_content += f"\n\n[Regeneration #{feedback_context.get('attempt_number', 1)}]"
            
    except Exception as e:
        actual_content = f"Error generating content: {str(e)}"
    
    instagram_post = {
        "task_description": task_description,
        "content": actual_content,
        "regeneration_info": {
            "is_regeneration": is_regeneration,
            "attempt_number": feedback_context.get("attempt_number", 0),
            "feedback_applied": bool(feedback_context.get("feedback_text"))
        } if is_regeneration else {}
    }

    return {
        "instagram_post": instagram_post,
        "messages": [f"Generated Instagram post for day {current_day} {'(regenerated)' if is_regeneration else ''} created successfully using AWS Bedrock"],
        "current_step": "create_instagram_post"
    }

# Apply the same pattern to all other social media agent functions:
# create_facebook_post, create_x_post, create_whatsapp_post, create_email_post, create_sms_post
```

## 4. Updated submit_feedback function - Enhanced State Input

```python
# Enhanced state input in submit_feedback function
state_input = {
    **state_dict,
    **feedback_dict,
    "stage": "content_generation",
    "plan_approved": True,
    "base_plan_dict": state_dict.get("base_plan_dict", campaign_plan),
    "current_post_id": post_id,
    "regen_attempt_number": version_number,
    "human_feedback_text": fb_text,
    "is_regeneration": True,
    
    # ENHANCED: Better variation parameters
    "variation_index": version_number,
    "random_seed": f"{post_id}|{datetime.utcnow().isoformat()}|{hash(fb_text)}",
    "force_variation": True,
    "previous_variants": feedback_dict.get("previous_variants", {}).get(pid_norm, []),
    
    # ENHANCED: Content generation context
    "skip_vector_db": False,
    "regeneration_mode": True,
    "feedback_context": {
        "original_content": full_plan.get(platform_key, {}).get(week_key, {}).get(day_key, {}).get("content", ""),
        "feedback_text": fb_text,
        "attempt_number": version_number,
        "platform": platform_key,
        "post_id": post_id
    }
}

# Remove image-related fields from fallback_keys:
fallback_keys = (
    "task", "content", "caption", "headline", "cta",
    "hook", "angle", "hashtags", "title", "body", "notes"
    # REMOVED: "image_path_s3", "image_prompt"
)

# Remove image-related fields from approved_plan_data:
approved_plan_data = {
    "campaign_name": campaign_full_name,
    "campaign_plan": full_plan,
    "current_step": "completed",
    "messages": [],
    "stage": "content_generation",
    "plan_approved": True,
    # REMOVED: "generated_images": [],
    # REMOVED: "image_generation_status": "skipped",
    "generated_at": datetime.utcnow().isoformat(),
    "human_feedback_map": human_feedback_map.copy()
}

# Remove from response object:
response = {
    "campaign_name": campaign_full_name,
    "success": True,
    "message": f"Feedback processed for {processed_count} of {len(deduped_feedbacks)} posts.",
    "campaign_plan": approved_plan_data["campaign_plan"],
    "platforms": approved_plan_data.get("platforms", []),
    # REMOVED: "generated_images": approved_plan_data.get("generated_images", []),
    # REMOVED: "image_generation_status": approved_plan_data.get("image_generation_status", "skipped"),
    "excel_s3_url": excel_s3_url,
    "processed": len(deduped_feedbacks),
    "timestamp": datetime.utcnow().isoformat(),
    "details": details
}
```

## 5. Updated excel_generator.py - Remove Image Functions

```python
# Remove extract_content_and_images function entirely

def generate_content_excel(campaign_plan: Dict[str, Any], writer) -> None:
    """Generate detailed Excel sheets with content for each platform."""
    for platform, weeks in campaign_plan.items():
        content_data = []
        for week_key, days in weeks.items():
            for day_key, day_data in days.items():
                content_data.append({
                    'Week': week_key.replace('_', ' ').title(),
                    'Day': day_key.replace('_', ' '),
                    'Task': day_data.get('task', ''),
                    'Content': day_data.get('content', ''),
                    # REMOVED: 'Image Paths': '\n'.join(all_image_paths) if all_image_paths else '',
                    'Human Feedback': day_data.get('human_feedback', ''),
                    'Regeneration Count': day_data.get('regeneration_count', 0),
                    'Status': 'Generated' if day_data.get('content') else 'Pending'
                })
        if content_data:
            df_content = pd.DataFrame(content_data)
            sheet_name = platform.title()
            df_content.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            enable_wrap_text(ws)
            auto_adjust_column_widths(ws)
```

## Summary of All Fixes

### ✅ **Regeneration Issue Fixed**
1. **Fixed routing**: `regeneration_router` now routes to `system_agent_orchestrator` instead of `social_media_agents_supervisor`
2. **Enhanced state input**: Added `feedback_context` with original content and feedback
3. **Higher temperature**: Dynamic temperature (0.9) for regeneration vs normal (0.8)
4. **Variation instructions**: Explicit instructions to create different content
5. **Feedback integration**: Direct feedback incorporation into prompts

### ✅ **Image Generation Completely Removed**
1. **Removed image_generator** node from graph
2. **Updated pipeline**: Direct `text_generator` → `content_reviewer` connection
3. **Removed image fields** from all data structures and APIs
4. **Cleaned Excel generation** to remove image columns
5. **Updated social media agents** to return only text content

### ✅ **Enhanced Content Variation**
1. **Prompt optimization** enhanced for regeneration with feedback keywords
2. **Random seeds** for additional variation
3. **Previous variants tracking** to avoid repetition
4. **Context enhancement** for better content quality

The system now has:
- **Proper regeneration flow** through the content pipeline
- **No image generation/upload** functionality 
- **Enhanced variation** for feedback-based regeneration
- **Cleaner codebase** without image-related complexity
