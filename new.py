# ... (rest of the function remains the same until context retrieval)

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
    collection_info = get_collection_info(collection_name, user_id=user_data.get('user_id'))
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

# Handle empty context gracefully (NEW: fallback instead of error)
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
# ... (rest of the function remains unchanged; it will now proceed even with fallback context)
