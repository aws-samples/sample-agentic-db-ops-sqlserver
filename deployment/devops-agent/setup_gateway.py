"""
setup_gateway.py - Create Cognito OAuth, AgentCore Gateway, and register Lambda targets.

Called by deploy_gateway.sh. Outputs gateway_config.json with connection details.

Usage:
    python3 setup_gateway.py            # Create
    python3 setup_gateway.py --cleanup  # Delete
"""

import json
import os
import sys

from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

REGION = os.environ["AWS_REGION"]
ROLE_ARN = os.environ["AGENTCORE_ROLE_ARN"]
ACCOUNT_ID = os.environ.get("AWS_ACCOUNTID", "")
GATEWAY_NAME = "dbops-mcp-gateway"
CONFIG_FILE = "gateway_config.json"

# Tool schemas for registration
HEALTH_TOOLS = [
    {"name": "get_cpu_utilization", "description": "Get CPU utilization timeline from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_database_load", "description": "Get database load (Active Average Sessions) from Performance Insights", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 24)"}}}},
    {"name": "get_extended_database_load", "description": "Get extended database load with wait event breakdown", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 24)"}}}},
    {"name": "get_database_connections", "description": "Get current database connection count from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_freeable_memory", "description": "Get freeable memory from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_free_storage", "description": "Get free storage space from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_iops", "description": "Get read/write IOPS from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_read_write_latency", "description": "Get read/write latency from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_network_throughput", "description": "Get network receive/transmit throughput from CloudWatch", "inputSchema": {"type": "object", "properties": {"minutes_back": {"type": "integer", "description": "Lookback window in minutes (default 1440)"}}}},
    {"name": "get_wait_events", "description": "Get top wait events from Performance Insights", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 1)"}}}},
    {"name": "get_top_sql", "description": "Get top SQL statements by load from Performance Insights", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 1)"}}}},
    {"name": "get_users", "description": "Get top database users by load from Performance Insights", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 1)"}}}},
    {"name": "get_applications", "description": "Get top applications by load from Performance Insights", "inputSchema": {"type": "object", "properties": {"hours_back": {"type": "integer", "description": "Lookback window in hours (default 1)"}}}},
    {"name": "send_email_notification", "description": "Send an alert notification via SNS", "inputSchema": {"type": "object", "properties": {"subject": {"type": "string", "description": "Email subject"}, "message": {"type": "string", "description": "Email body"}, "severity": {"type": "string", "description": "INFO, WARNING, or CRITICAL"}}, "required": ["subject", "message"]}},
]

QUERY_TOOLS = [
    {"name": "check_query_store_enabled", "description": "Check if Query Store is enabled on the database", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_query_store_top_queries", "description": "Get top queries from Query Store by CPU, duration, IO, or memory", "inputSchema": {"type": "object", "properties": {"metric": {"type": "string", "description": "Sort metric: cpu, duration, io, memory (default cpu)"}, "top_n": {"type": "integer", "description": "Number of results (default 10)"}}}},
    {"name": "get_query_store_regressed_queries", "description": "Get queries that have regressed in performance", "inputSchema": {"type": "object", "properties": {"metric": {"type": "string", "description": "Metric to compare: cpu, duration, io (default cpu)"}}}},
    {"name": "get_query_store_wait_stats", "description": "Get wait statistics from Query Store", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_query_execution_history", "description": "Get execution history for a specific query", "inputSchema": {"type": "object", "properties": {"query_id": {"type": "integer", "description": "Query Store query ID"}}, "required": ["query_id"]}},
    {"name": "get_query_store_plan_summary", "description": "Get plan summary for a specific query", "inputSchema": {"type": "object", "properties": {"query_id": {"type": "integer", "description": "Query Store query ID"}}, "required": ["query_id"]}},
    {"name": "get_slow_queries", "description": "Get currently running slow queries", "inputSchema": {"type": "object", "properties": {"threshold_seconds": {"type": "integer", "description": "Minimum elapsed time in seconds (default 5)"}}}},
    {"name": "get_blocking_sessions", "description": "Get current blocking session chains", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_query_plan_from_cache", "description": "Get execution plan from plan cache for a query", "inputSchema": {"type": "object", "properties": {"sql_text_pattern": {"type": "string", "description": "SQL text pattern to search for"}}, "required": ["sql_text_pattern"]}},
    {"name": "get_expensive_queries_from_cache", "description": "Get most expensive queries from plan cache", "inputSchema": {"type": "object", "properties": {"metric": {"type": "string", "description": "Sort metric: cpu, reads, duration (default cpu)"}, "top_n": {"type": "integer", "description": "Number of results (default 10)"}}}},
    {"name": "suggest_indexes", "description": "Get missing index suggestions from SQL Server", "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string", "description": "Optional: filter to specific table"}}}},
    {"name": "get_index_usage", "description": "Get index usage statistics", "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string", "description": "Optional: filter to specific table"}}}},
    {"name": "send_email_notification", "description": "Send an alert notification via SNS", "inputSchema": {"type": "object", "properties": {"subject": {"type": "string", "description": "Email subject"}, "message": {"type": "string", "description": "Email body"}, "severity": {"type": "string", "description": "INFO, WARNING, or CRITICAL"}}, "required": ["subject", "message"]}},
]


def deploy():
    client = GatewayClient(region_name=REGION)

    # Create MCP Gateway with IAM auth
    print("  Creating MCP Gateway (IAM auth)...")
    gateway = client.create_mcp_gateway(
        name=GATEWAY_NAME,
        role_arn=ROLE_ARN,
        authorizer_type="AWS_IAM",
    )
    gateway_url = gateway.get("gatewayUrl") or gateway.get("gateway_url")
    print(f"  ✅ Gateway created: {gateway_url}")

    # Register health tools target
    health_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:dbops-health-tools"
    print("  Registering dbops-health-tools target (14 tools)...")
    client.create_mcp_gateway_target(
        gateway=gateway,
        name="dbops-health-tools",
        target_type="lambda",
        target_payload={
            "lambdaArn": health_arn,
            "toolSchema": {"inlinePayload": HEALTH_TOOLS},
        },
    )
    print("  ✅ Health tools registered")

    # Register query tools target
    query_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:dbops-query-tools"
    print("  Registering dbops-query-tools target (13 tools)...")
    client.create_mcp_gateway_target(
        gateway=gateway,
        name="dbops-query-tools",
        target_type="lambda",
        target_payload={
            "lambdaArn": query_arn,
            "toolSchema": {"inlinePayload": QUERY_TOOLS},
        },
    )
    print("  ✅ Query tools registered")

    # Save config
    config = {
        "gateway_url": gateway_url,
        "region": REGION,
        "total_tools": 27,
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  ✅ Configuration saved to {CONFIG_FILE}")


def cleanup():
    client = GatewayClient(region_name=REGION)
    print("  Deleting MCP Gateway...")
    try:
        client.delete_mcp_gateway(name=GATEWAY_NAME)
        print("  ✅ Gateway deleted")
    except Exception as e:
        print(f"  ⚠️  {e}")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        if not ACCOUNT_ID:
            import boto3
            ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
            os.environ["AWS_ACCOUNTID"] = ACCOUNT_ID
        deploy()
