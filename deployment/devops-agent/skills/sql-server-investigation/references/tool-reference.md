# Tool Reference

## Health Metrics Thresholds

| Metric | Normal | Warning | Critical | Tool |
|--------|--------|---------|----------|------|
| CPU Utilization | < 70% | 70–90% | > 90% | `get_cpu_utilization` |
| Database Load (AAS) | < 2 | 2–4 | > 4 | `get_database_load` |
| Connections | < 80% of max | 80–90% of max | > 90% of max | `get_database_connections` |
| Freeable Memory | > 2 GB | 1–2 GB | < 1 GB | `get_freeable_memory` |
| Free Storage | > 20% | 10–20% | < 10% | `get_free_storage` |
| Read/Write Latency | < 5 ms | 5–20 ms | > 20 ms | `get_read_write_latency` |

## Tool Parameters

| Tool | Key Parameter | Default | Usage |
|------|--------------|---------|-------|
| `get_cpu_utilization` | `minutes_back` | 1440 | Lookback window (default 24h) |
| `get_database_load` | `hours_back` | 24 | Lookback window in hours |
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
