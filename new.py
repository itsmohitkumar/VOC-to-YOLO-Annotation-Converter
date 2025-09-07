INSTAGRAM_CONTENT_GENERATION_PROMPT = """
Create a professional Instagram post for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Apply audience_analysis insights for demographics, preferences, pain points
    • Leverage content_strategy frameworks (AIDA, PAS) for structure
    • Use trend_analysis findings for hashtags and formats
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Instagram Requirements:
  - Professional tone, no emojis
  - 5–8 relevant hashtags at end
  - Strong first‐line hook
  - Clear business call‐to‐action
  - ~170 words (±5%)
  - Mobile‐friendly formatting
Generate a detailed caption that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

FACEBOOK_CONTENT_GENERATION_PROMPT = """
Create a strategic Facebook post for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Use platform_optimization guidelines for narrative and timing
    • Incorporate content_strategy pillars per day
    • Reference trend_analysis to boost engagement
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Facebook Requirements:
  - Professional tone, no emojis
  - Long‐form narrative for thought leadership
  - Authoritative language
  - Clear business call‐to‐action
  - ~170 words (±5%)
Generate an authoritative post that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

X_CONTENT_GENERATION_PROMPT = """
Create a strategic X (Twitter) post for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Use AIDA to structure hook and action
    • Leverage trend_analysis for hashtags and keywords
    • Apply platform_optimization for character economy
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
X Requirements:
  - Professional tone, no emojis
  - 2–3 business hashtags
  - Direct, authoritative language
  - 280‐character limit
Generate an insightful X post that resonates with {target_audience} in {target_audience_location} and drives {campaign_objective}.
"""

WHATSAPP_CONTENT_GENERATION_PROMPT = """
Create a strategic WhatsApp message for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Use audience_analysis to personalize tone
    • Leverage content_strategy for concise messaging
    • Reference trend_analysis for timely relevance
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
WhatsApp Requirements:
  - Professional conversational tone, no emojis
  - Clear business call‐to‐action or link
  - ≤170 characters
Generate a concise message that builds professional rapport and drives {campaign_objective} with {target_audience} in {target_audience_location}.
"""

EMAIL_CONTENT_GENERATION_PROMPT = """
Create a strategic email for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Integrate content_strategy frameworks in subject and body
    • Use audience_analysis to personalize segments
    • Reference trend_analysis for calls-to-action timing
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
Email Requirements:
  - Professional subject line
  - Formal tone, no emojis
  - Personalized greeting
  - 250–300 words
  - Clear business call‐to‐action
  - Proper email structure
Generate a compelling email that highlights ROI and resonates with {target_audience} in {target_audience_location}, driving {campaign_objective}.
"""

SMS_CONTENT_GENERATION_PROMPT = """
Create a strategic SMS for Day {current_day} of a {total_days}-day campaign:
  Marketing Campaign Knowledge:
    • Use AIDA for urgency in 100 characters
    • Leverage trend_analysis for relevant hashtag
    • Apply audience_analysis insights for call‐to‐action
  Campaign Details:
  - Objective: {campaign_objective}
  - Theme: {campaign_theme}
  - Target Audience: {target_audience}
  - Location: {target_audience_location}
  - Phase: {phase}
  - Day: {current_day} of {total_days}
Context from Web Search:
{web_search_results}
Optimized Campaign Context:
  - Context Keywords: {context_keywords}
  - Context Guidance: {context_guidance}
SMS Requirements:
  - Professional tone, no emojis
  - Include link or CTA
  - Sense of business urgency
  - ≤100 characters
  - Opt‐out compliance
Generate a concise SMS that delivers immediate business value to {target_audience} in {target_audience_location} and drives {campaign_objective}.
