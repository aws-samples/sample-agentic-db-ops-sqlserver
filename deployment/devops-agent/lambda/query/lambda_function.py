"""Lambda handler for query performance tools exposed via AgentCore Gateway."""

import json
from query_performance_tools import (
    check_query_store_enabled, get_blocking_sessions,
    get_expensive_queries_from_cache, get_index_usage,
    get_query_execution_history, get_query_plan_from_cache,
    get_query_store_plan_summary, get_query_store_regressed_queries,
    get_query_store_top_queries, get_query_store_wait_stats,
    get_slow_queries, suggest_indexes,
    send_email_notification,
)

TOOL_MAP = {
    "check_query_store_enabled": check_query_store_enabled,
    "get_query_store_top_queries": get_query_store_top_queries,
    "get_query_store_regressed_queries": get_query_store_regressed_queries,
    "get_query_store_wait_stats": get_query_store_wait_stats,
    "get_query_execution_history": get_query_execution_history,
    "get_query_store_plan_summary": get_query_store_plan_summary,
    "get_slow_queries": get_slow_queries,
    "get_blocking_sessions": get_blocking_sessions,
    "get_query_plan_from_cache": get_query_plan_from_cache,
    "get_expensive_queries_from_cache": get_expensive_queries_from_cache,
    "suggest_indexes": suggest_indexes,
    "get_index_usage": get_index_usage,
    "send_email_notification": send_email_notification,
}


def lambda_handler(event, context):
    tool_name = ''
    if hasattr(context, 'client_context') and context.client_context and hasattr(context.client_context, 'custom') and context.client_context.custom:
        tool_name = context.client_context.custom.get('bedrockAgentCoreToolName', '')

    if '___' in tool_name:
        tool_name = tool_name.split('___', 1)[1]

    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}", "available_tools": list(TOOL_MAP.keys())})

    try:
        result = func(**event) if event else func()
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
