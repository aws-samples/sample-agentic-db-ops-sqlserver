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
import time
import logging

from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# The toolkit's gateway logger dumps full target payloads at INFO. Quiet it to
# WARNING so deploy output stays readable (set to INFO/DEBUG to troubleshoot).
logging.getLogger("bedrock_agentcore.gateway").setLevel(logging.WARNING)

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


def _find_gateway_by_name(cp, name):
    """Return the full gateway dict (from get_gateway) if one exists with this name, else None."""
    token = None
    while True:
        kwargs = {"maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        resp = cp.list_gateways(**kwargs)
        for gw in resp.get("items", []):
            if gw.get("name") == name:
                return cp.get_gateway(gatewayIdentifier=gw["gatewayId"])
        token = resp.get("nextToken")
        if not token:
            return None


def _find_target_by_name(cp, gateway_id, name):
    """Return the target summary dict if a target with this name exists on the gateway, else None."""
    token = None
    while True:
        kwargs = {"gatewayIdentifier": gateway_id, "maxResults": 50}
        if token:
            kwargs["nextToken"] = token
        resp = cp.list_gateway_targets(**kwargs)
        for t in resp.get("items", []):
            if t.get("name") == name:
                return t
        token = resp.get("nextToken")
        if not token:
            return None


def _wait_gateway_ready(cp, gateway_id):
    for _ in range(60):
        g = cp.get_gateway(gatewayIdentifier=gateway_id)
        status = g.get("status")
        if status == "READY":
            return g
        if status in ("FAILED", "DELETING"):
            raise RuntimeError(f"Gateway entered unexpected state: {status} ({g.get('statusReasons')})")
        time.sleep(5)
    return cp.get_gateway(gatewayIdentifier=gateway_id)


def deploy():
    client = GatewayClient(region_name=REGION)
    cp = client.client

    # Create (or reuse) the MCP Gateway with AWS IAM auth.
    # The toolkit's create_mcp_gateway() hardcodes authorizerType=CUSTOM_JWT (Cognito)
    # and exposes no way to request IAM auth, so we call the underlying
    # bedrock-agentcore-control create_gateway API directly with AWS_IAM. The toolkit's
    # create_mcp_gateway_target() only reads gatewayId + roleArn from the gateway dict,
    # so the raw boto3 response is compatible for target registration below.
    existing = _find_gateway_by_name(cp, GATEWAY_NAME)
    if existing:
        gateway = existing
        print(f"  ♻️  Reusing existing gateway: {gateway['gatewayId']}")
        gateway = _wait_gateway_ready(cp, gateway["gatewayId"])
    else:
        print("  Creating MCP Gateway (AWS IAM auth)...")
        gateway = cp.create_gateway(
            name=GATEWAY_NAME,
            roleArn=ROLE_ARN,
            protocolType="MCP",
            authorizerType="AWS_IAM",
            protocolConfiguration={"mcp": {"searchType": "SEMANTIC"}},
        )
        gateway = _wait_gateway_ready(cp, gateway["gatewayId"])
    gateway_url = gateway.get("gatewayUrl") or gateway.get("gateway_url")
    print(f"  ✅ Gateway ready: {gateway_url}")

    # Register targets (skip any that already exist so re-runs are idempotent).
    targets = [
        ("dbops-health-tools", "14 tools", HEALTH_TOOLS),
        ("dbops-query-tools", "13 tools", QUERY_TOOLS),
    ]
    for target_name, label, schema in targets:
        if _find_target_by_name(cp, gateway["gatewayId"], target_name):
            print(f"  ♻️  Target {target_name} already exists — skipping")
            continue
        lambda_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:{target_name}"
        print(f"  Registering {target_name} target ({label})...")
        client.create_mcp_gateway_target(
            gateway=gateway,
            name=target_name,
            target_type="lambda",
            target_payload={
                "lambdaArn": lambda_arn,
                "toolSchema": {"inlinePayload": schema},
            },
        )
        print(f"  ✅ {target_name} registered")

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
    # The toolkit has no delete_mcp_gateway in this version, so use the boto3
    # control client directly. A gateway can't be deleted while it has targets,
    # so delete all targets first, then the gateway. Find the gateway by name.
    client = GatewayClient(region_name=REGION)
    cp = client.client

    print("  Looking up gateway by name...")
    gateway_id = None
    paginator_token = None
    while True:
        kwargs = {"maxResults": 50}
        if paginator_token:
            kwargs["nextToken"] = paginator_token
        resp = cp.list_gateways(**kwargs)
        for gw in resp.get("items", []):
            if gw.get("name") == GATEWAY_NAME:
                gateway_id = gw.get("gatewayId")
                break
        paginator_token = resp.get("nextToken")
        if gateway_id or not paginator_token:
            break

    if not gateway_id:
        print(f"  ℹ️  No gateway named {GATEWAY_NAME} found — nothing to delete")
        return

    print(f"  Deleting targets for {gateway_id}...")
    tk = None
    while True:
        kwargs = {"gatewayIdentifier": gateway_id, "maxResults": 50}
        if tk:
            kwargs["nextToken"] = tk
        tresp = cp.list_gateway_targets(**kwargs)
        for t in tresp.get("items", []):
            tid = t.get("targetId")
            try:
                cp.delete_gateway_target(gatewayIdentifier=gateway_id, targetId=tid)
                print(f"    ✅ Deleted target {tid}")
            except Exception as e:
                print(f"    ⚠️  target {tid}: {e}")
        tk = tresp.get("nextToken")
        if not tk:
            break

    print("  Deleting MCP Gateway...")
    try:
        cp.delete_gateway(gatewayIdentifier=gateway_id)
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
