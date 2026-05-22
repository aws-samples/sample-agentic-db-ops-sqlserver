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
    tool_name = event.get("name") or event.get("tool_name")
    arguments = event.get("arguments") or event.get("input", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    func = TOOL_MAP.get(tool_name)
    if not func:
        return {"error": f"Unknown tool: {tool_name}", "available": list(TOOL_MAP.keys())}

    try:
        return {"result": func(**arguments)}
    except Exception as e:
        return {"error": str(e), "tool": tool_name}
