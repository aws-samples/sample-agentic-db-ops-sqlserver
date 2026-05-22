"""Lambda handler for health tools exposed via AgentCore Gateway."""

import json
from database_health_tools import (
    get_applications, get_cpu_utilization, get_database_connections,
    get_database_load, get_extended_database_load, get_free_storage,
    get_freeable_memory, get_iops, get_network_throughput,
    get_read_write_latency, get_top_sql, get_users, get_wait_events,
    send_email_notification,
)

TOOL_MAP = {
    "get_cpu_utilization": get_cpu_utilization,
    "get_database_load": get_database_load,
    "get_extended_database_load": get_extended_database_load,
    "get_database_connections": get_database_connections,
    "get_freeable_memory": get_freeable_memory,
    "get_free_storage": get_free_storage,
    "get_iops": get_iops,
    "get_read_write_latency": get_read_write_latency,
    "get_network_throughput": get_network_throughput,
    "get_wait_events": get_wait_events,
    "get_top_sql": get_top_sql,
    "get_users": get_users,
    "get_applications": get_applications,
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
