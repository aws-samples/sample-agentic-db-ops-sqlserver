"""
Lambda handler for query performance tools exposed via AgentCore Gateway.

Routes MCP tool calls to the appropriate function in query_performance_tools.py.
"""

import json
import os

from query_performance_tools import (
    check_query_store_enabled,
    get_blocking_sessions,
    get_expensive_queries_from_cache,
    get_index_usage,
    get_query_execution_history,
    get_query_plan_from_cache,
    get_query_store_plan_summary,
    get_query_store_regressed_queries,
    get_query_store_top_queries,
    get_query_store_wait_stats,
    get_slow_queries,
    suggest_indexes,
)
from shared_utils import send_email_notification

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
    tool_name = event.get("name") or event.get("tool_name")
    arguments = event.get("arguments") or event.get("input", {})

    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    func = TOOL_MAP.get(tool_name)
    if not func:
        return {"error": f"Unknown tool: {tool_name}", "available": list(TOOL_MAP.keys())}

    try:
        result = func(**arguments)
        return {"result": result}
    except Exception as e:
        return {"error": str(e), "tool": tool_name}
