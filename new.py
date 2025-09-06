def get_campaign_status(username: str, campaign_name: str) -> dict:
    query = text("""
        SELECT
            approved_plan,
            regeneration_count,
            approved_plan_v1,
            approved_plan_v2,
            approved_plan_v3
        FROM agentic_campaign_planner
        WHERE TRIM(LOWER(username)) = TRIM(LOWER(:username))
          AND TRIM(LOWER(campaign_name)) = TRIM(LOWER(:campaign_name))
    """)
    params = {"username": username, "campaign_name": campaign_name}
    result = execute_query(query, params=params, fetch_one=True)
    if result:
        return {
            "approved_plan": bool(result[0]) if result[0] is not None else False,
            "regeneration_count": int(result[1] or 0),
            "has_approved_plan_v1": result[2] is not None,
            "has_approved_plan_v2": result[3] is not None,
            "has_approved_plan_v3": result[4] is not None,
        }
    return {
        "approved_plan": False,
        "regeneration_count": 0,
        "has_approved_plan_v1": False,
        "has_approved_plan_v2": False,
        "has_approved_plan_v3": False,
    }
