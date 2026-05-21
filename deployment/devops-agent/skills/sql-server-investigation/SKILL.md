---
name: sql-server-investigation
description: |
  Investigation procedures for RDS SQL Server performance issues using AgentCore
  Gateway MCP tools. Use this skill when investigating database latency, high CPU,
  connection exhaustion, blocking sessions, slow queries, query regressions,
  or storage capacity issues on SQL Server instances.
---

# SQL Server Investigation Skill

Structured troubleshooting methodology for Amazon RDS for SQL Server using 27 MCP diagnostic tools.

## Investigation Workflow

Follow these steps in order for every investigation:

### Step 1: TRIAGE — Assess Overall Health

Always start here regardless of the reported symptom:

1. `get_cpu_utilization` — current and peak CPU percentage
2. `get_database_load` — Active Average Sessions (AAS)
3. `get_database_connections` — connection count vs limits
4. `get_freeable_memory` — memory pressure and trend

**Severity thresholds:**

| Severity | Criteria |
|----------|----------|
| CRITICAL | CPU > 90% OR AAS > 8 OR connections near max OR memory < 1 GB |
| WARNING | CPU > 70% OR AAS > 4 OR memory declining OR connections > 70% of max |
| INFO | All metrics within normal ranges |

### Step 2: DIAGNOSE — Identify Bottleneck Type

Call `get_wait_events` and route based on dominant wait type:

| Dominant Wait Type | Bottleneck | Go To |
|-------------------|-----------|-------|
| CPU | Compute-bound queries | Step 3a |
| Lock / LCK_M_* | Blocking and locking | Step 3b |
| IO / PAGEIOLATCH | Storage I/O saturation | Step 3c |
| Memory / RESOURCE_SEMAPHORE | Memory pressure | Step 3d |
| Network / ASYNC_NETWORK_IO | Network saturation | Step 3e |

### Step 3: DRILL DOWN — Investigate Specific Area

#### 3a: CPU-Bound

1. `get_query_store_top_queries` with metric="cpu"
2. `get_expensive_queries_from_cache` with metric="cpu"
3. `suggest_indexes` — missing indexes causing table scans

#### 3b: Blocking

1. `get_blocking_sessions` — blocking chains and head blocker
2. `get_slow_queries` — long-running queries holding locks
3. `get_query_store_wait_stats` — lock wait times

#### 3c: IO Saturation

1. `get_iops` — read/write IOPS vs provisioned limits
2. `get_read_write_latency` — latency spikes
3. `get_query_store_top_queries` with metric="io"

#### 3d: Memory Pressure

1. `get_freeable_memory` — memory trend over time
2. `get_query_store_top_queries` with metric="memory"
3. `get_database_load` — correlation with load

#### 3e: Network

1. `get_network_throughput` — bandwidth utilization
2. `get_database_connections` — connection churn
3. `get_applications` — chatty applications

### Step 4: CORRELATE — Cross-Reference Findings

- `get_query_store_regressed_queries` — recent regression or chronic?
- `get_extended_database_load` — current vs historical baseline
- `get_users` — which users contribute most load
- `get_applications` — which applications drive workload

### Step 5: RECOMMEND — Produce Actionable Output

Structure your response as:

1. **Severity** — CRITICAL / WARNING / INFO with supporting thresholds
2. **Root Cause** — One-sentence diagnosis with metric values
3. **Evidence** — Specific numbers, timestamps, percentages
4. **Recommendations** — Ordered list, most impactful first
5. **Queries to Investigate** — Specific SQL statements to review
6. **Index Suggestions** — CREATE INDEX statements if applicable
