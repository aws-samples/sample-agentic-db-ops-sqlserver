# Tool Reference

## Health Metrics Thresholds

Host metrics are read by the DevOps Agent natively (CloudWatch and Performance
Insights / Database Insights); they are not MCP tools. Use these thresholds during
triage.

| Metric | Normal | Warning | Critical | Source |
|--------|--------|---------|----------|--------|
| CPU Utilization | < 70% | 70 to 90% | > 90% | CloudWatch |
| Database Load (AAS) | < 2 | 2 to 4 | > 4 | Performance Insights |
| Connections | < 80% of max | 80 to 90% of max | > 90% of max | CloudWatch |
| Freeable Memory | > 2 GB | 1 to 2 GB | < 1 GB | CloudWatch |
| Free Storage | > 20% | 10 to 20% | < 10% | CloudWatch |
| Read/Write Latency | < 5 ms | 5 to 20 ms | > 20 ms | CloudWatch |

## Tool Parameters

These are the MCP query tools the agent calls for SQL-level detail.

| Tool | Key Parameter | Default | Usage |
|------|--------------|---------|-------|
| `get_query_store_top_queries` | `metric` | `"cpu"` | Sort by: `"cpu"`, `"duration"`, `"io"`, `"memory"` |
| `get_query_store_top_queries` | `top_n` | 10 | Number of results to return |
| `get_slow_queries` | `threshold_seconds` | 5 | Minimum elapsed time to qualify |
| `get_expensive_queries_from_cache` | `metric` | `"cpu"` | Sort by: `"cpu"`, `"reads"`, `"duration"` |
| `suggest_indexes` | `table_name` | None | Optional filter to specific table |
| `send_email_notification` | `severity` | `"INFO"` | `"INFO"`, `"WARNING"`, `"CRITICAL"` |

## Wait Event Categories

| Wait Category | Common Waits | Indicates |
|--------------|-------------|-----------|
| CPU | SOS_SCHEDULER_YIELD, CXPACKET | Compute-bound workload |
| Lock | LCK_M_X, LCK_M_S, LCK_M_U | Blocking between sessions |
| IO | PAGEIOLATCH_SH, PAGEIOLATCH_EX, WRITELOG | Storage bottleneck |
| Memory | RESOURCE_SEMAPHORE, CMEMTHREAD | Memory pressure |
| Network | ASYNC_NETWORK_IO | Client not consuming results fast enough |
