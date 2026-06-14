---
name: sql-server-investigation
description: Incident investigation procedures for Amazon RDS for SQL Server
  performance issues including blocking and lock contention, plan regression,
  slow or high-impact queries, and missing indexes. Use this skill when
  investigating SQL Server database latency, high CPU, blocked sessions, query
  timeouts, or read/write performance degradation. Triggers on requests like
  "investigate SQL Server blocking", "RDS SQL Server high CPU", "query timeout
  RCA", "plan regression", or "why is my SQL Server slow".
metadata:
  version: "1.0.0"
  aws-devops-agent-skills.agent-types: "Incident RCA"
  aws-devops-agent-skills.aws-services: "Amazon RDS"
  aws-devops-agent-skills.technical-domains: "Databases"
---

# SQL Server Investigation

Structured troubleshooting methodology for Amazon RDS for SQL Server. Work from
the lightweight signal outward: use native AWS APIs to triage and localize the
problem, then use the MCP tools to resolve the session-, plan-, and index-level
detail those APIs cannot reach.

## Investigation Workflow

Follow these steps in order for every investigation.

### Step 1: TRIAGE — Assess Overall Health

Always start here regardless of the reported symptom. Retrieve current values and
active alarms from native AWS APIs:

```
cloudwatch.DescribeAlarms     # active alarms on the instance
cloudwatch.GetMetricData      # CPUUtilization, DatabaseConnections,
                              # FreeableMemory, FreeStorageSpace
pi.GetResourceMetrics         # db.load — Average Active Sessions (AAS)
```

**Severity thresholds:**

| Severity | Criteria |
|----------|----------|
| CRITICAL | CPU > 90% OR AAS > 8 OR connections near max OR FreeableMemory < 1 GB |
| WARNING | CPU > 70% OR AAS > 4 OR memory declining OR connections > 70% of max |
| INFO | All metrics within normal ranges |

### Step 2: DIAGNOSE — Identify Bottleneck Type

Use Performance Insights to find the dominant wait over the incident window, then
route based on the wait type:

```
pi.GetResourceMetrics         # db.load grouped by wait event
pi.DescribeDimensionKeys      # top SQL by database time
```

| Dominant Wait Type | Bottleneck | Go To |
|-------------------|-----------|-------|
| CPU | Compute-bound queries | Step 3a |
| Lock / `LCK_M_*` | Blocking and locking | Step 3b |
| IO / `PAGEIOLATCH` | Storage I/O saturation | Step 3c |
| Memory / `RESOURCE_SEMAPHORE` | Memory pressure | Step 3d |
| Network / `ASYNC_NETWORK_IO` | Network saturation | Step 3e |

### Step 3: DRILL DOWN — Investigate the Specific Area

#### 3a: CPU-Bound

```
get_query_store_top_queries        # metric="cpu" — top CPU consumers with plan_ids
get_expensive_queries_from_cache   # metric="cpu" — heavy queries in plan cache
suggest_indexes                    # missing indexes causing scans
```

#### 3b: Blocking

```
get_blocking_sessions              # blocking chains and head blocker
get_slow_queries                   # long-running statements holding locks
get_query_store_wait_stats         # lock wait time by query
```

#### 3c: IO Saturation

```
cloudwatch.GetMetricData           # ReadIOPS, WriteIOPS vs provisioned limits
cloudwatch.GetMetricData           # ReadLatency, WriteLatency spikes
get_query_store_top_queries        # metric="io" — heaviest I/O queries
```

#### 3d: Memory Pressure

```
cloudwatch.GetMetricData           # FreeableMemory trend over time
get_query_store_top_queries        # metric="memory" — memory-grant-heavy queries
pi.GetResourceMetrics              # db.load correlation with memory waits
```

#### 3e: Network

```
cloudwatch.GetMetricData           # NetworkReceiveThroughput, NetworkTransmitThroughput
cloudwatch.GetMetricData           # DatabaseConnections — connection churn
pi.DescribeDimensionKeys           # connected applications driving traffic
```

### Step 4: CORRELATE — Cross-Reference Findings

```
get_query_store_regressed_queries  # recent regression or chronic? (MCP)
pi.GetResourceMetrics              # current load vs historical baseline
pi.DescribeDimensionKeys           # which users and applications contribute most load
```

### Step 5: RECOMMEND — Produce Actionable Output

Structure the response as:

1. **Severity** — CRITICAL / WARNING / INFO with the supporting thresholds.
2. **Root cause** — one-sentence diagnosis with metric values.
3. **Evidence** — specific numbers, timestamps, percentages, session IDs, SQL
   text, `plan_id`s, and regression factor where applicable.
4. **Recommendations** — ordered, most impactful first.
5. **Queries to investigate** — specific SQL statements to review.
6. **Index suggestions** — `CREATE INDEX` statements if applicable.

## Data Source Boundaries

Prefer native AWS APIs for everything they expose; reserve the MCP tools for
SQL-level detail those APIs cannot reach.

Available natively through AWS APIs (prefer these):

- CloudWatch metrics — CPU, memory, storage, IOPS, latency, connections.
- Performance Insights / Database Insights — database load, top wait events, top
  SQL by database time, active sessions.
- CloudWatch Logs — SQL Server error log, including deadlock traces (trace flags
  1204/1222).
- CloudTrail — parameter group changes, failovers, configuration modifications.

Only available through the MCP tools (direct SQL connection required) — for
example:

- The exact blocking chain and head blocker (`get_blocking_sessions`).
- Execution-plan regression history (`get_query_store_regressed_queries`).
- Top resource-consuming queries with plan_ids (`get_query_store_top_queries`).
- Queries and plans from the cache (`get_expensive_queries_from_cache`,
  `get_query_plan_from_cache`).
- Live missing-index recommendations and existing index usage
  (`suggest_indexes`, `get_index_usage`).
