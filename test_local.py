#!/usr/bin/env python3
"""Local test for any agent — runs directly without AgentCore runtime."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "db-engines", "sql-server"))

from strands import Agent
from strands.models import BedrockModel
from config.settings import AWS_REGION, LLM_MODEL

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

AGENTS = {
    "database_health": {
        "tools_module": "tools.database_health_tools",
        "tools": [
            "get_database_load", "get_extended_database_load", "get_wait_events", "get_top_sql",
            "get_users", "get_applications", "get_database_connections", "get_cpu_utilization",
            "get_free_storage", "get_read_write_latency", "get_iops", "get_network_throughput",
            "get_freeable_memory", "send_email_notification"
        ],
        "prompt": "You are an RDS SQL Server performance specialist using Database Insights and CloudWatch metrics.",
    },
    "query_performance": {
        "tools_module": "tools.query_performance_tools",
        "tools": [
            "check_query_store_enabled", "get_query_store_top_queries", "get_query_store_regressed_queries",
            "get_query_store_wait_stats", "get_query_execution_history", "get_query_store_plan_summary",
            "get_slow_queries", "get_blocking_sessions", "get_query_plan_from_cache",
            "get_expensive_queries_from_cache", "suggest_indexes", "get_index_usage", "send_email_notification"
        ],
        "prompt": "You are an RDS SQL Server query performance specialist. Always call check_query_store_enabled() first.",
    },
    "security_audit": {
        "tools_module": "tools.security_audit_tools",
        "tools": [
            "check_tde_status", "check_backup_encryption", "get_failed_login_attempts",
            "get_rds_events", "get_configuration_changes_from_cloudtrail",
            "check_rds_security_settings", "check_rds_audit_settings", "send_email_notification"
        ],
        "prompt": "You are an RDS SQL Server security audit specialist.",
    },
    "data_lifecycle": {
        "tools_module": "tools.data_lifecycle_tools",
        "tools": [
            "get_storage_metrics", "get_iops_trends", "get_throughput_trends", "get_latency_trends",
            "get_queue_depth_trends", "analyze_storage_growth", "get_storage_configuration",
            "recommend_storage_upgrade", "get_database_size", "get_table_sizes", "get_index_sizes",
            "identify_old_data", "get_fragmentation_status", "get_tempdb_size",
            "get_tempdb_space_usage_by_session", "get_tempdb_space_usage_by_query",
            "get_tempdb_contention", "get_tempdb_io_stats", "check_tempdb_file_configuration",
            "get_temp_table_usage", "get_version_store_usage", "validate_tempdb_configuration",
            "analyze_tempdb_bottleneck", "check_backup_status", "send_email_notification"
        ],
        "prompt": "You are an RDS SQL Server data lifecycle and storage specialist.",
    },
}

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <agent_name> \"<prompt>\"")
        print(f"Available: {list(AGENTS.keys())}")
        sys.exit(1)

    name, prompt = sys.argv[1], sys.argv[2]
    if name not in AGENTS:
        print(f"Unknown agent: {name}. Available: {list(AGENTS.keys())}")
        sys.exit(1)

    cfg = AGENTS[name]
    mod = __import__(cfg["tools_module"], fromlist=cfg["tools"])
    tools = [getattr(mod, t) for t in cfg["tools"]]

    agent = Agent(system_prompt=cfg["prompt"], model=model, tools=tools)
    print(f"Agent: {name}\nPrompt: {prompt}\n")
    result = agent(prompt)
    print(f"\n{'='*60}\n{result.message['content'][0]['text']}")

if __name__ == "__main__":
    main()
