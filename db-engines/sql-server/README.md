# SQL Server Agents

5 specialized AI agents for autonomous Amazon RDS for SQL Server operations. Agents import tools from `tools/` and configuration from `config/settings.py`.

## Structure

```
sql-server/
├── agents/                            # Thin agent definitions
│   ├── database_health_agent.py       # Imports from tools/database_health_tools.py
│   ├── query_performance_agent.py     # Imports from tools/query_performance_tools.py
│   ├── security_audit_agent.py        # Imports from tools/security_audit_tools.py
│   ├── data_lifecycle_agent.py        # Imports from tools/data_lifecycle_tools.py
│   └── supervisor_agent.py            # Imports from tools/supervisor_tools.py
├── tools/                             # @tool functions grouped by domain
│   ├── database_health_tools.py       # 14 tools: Database Insights, CloudWatch
│   ├── query_performance_tools.py     # 13 tools: DMVs, Query Store
│   ├── security_audit_tools.py        # 8 tools: RDS API, CloudWatch Logs, CloudTrail
│   ├── data_lifecycle_tools.py        # 25 tools: CloudWatch, DMVs, RDS API
│   └── supervisor_tools.py            # 10 tools: A2A orchestration
├── config/
│   └── settings.py                    # Environment variables, VPC endpoint docs
└── requirements.txt
```

## Agents

| Agent | File | Tools File | Tools | Data Sources |
|-------|------|-----------|-------|-------------|
| 📊 Database Health | `agents/database_health_agent.py` | `tools/database_health_tools.py` | 14 | Database Insights, CloudWatch |
| ⚡ Query Performance | `agents/query_performance_agent.py` | `tools/query_performance_tools.py` | 13 | SQL Server DMVs, Query Store |
| 🔒 Security Audit | `agents/security_audit_agent.py` | `tools/security_audit_tools.py` | 8 | RDS API, CloudWatch Logs, CloudTrail |
| 💾 Data Lifecycle | `agents/data_lifecycle_agent.py` | `tools/data_lifecycle_tools.py` | 25 | CloudWatch, DMVs, RDS API |
| 🎯 Supervisor | `agents/supervisor_agent.py` | `tools/supervisor_tools.py` | 10 | AgentCore A2A |

## Setup

### 1. Configure

Edit `config/settings.py` or set environment variables. See [config/README.md](config/README.md) for the full list including VPC endpoint requirements.

### 2. Install dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Deploy

From the repo root:

```bash
./deployment/agentcore/deploy.sh
```

### 4. Test

```bash
agentcore invoke --agent database_health_agent '{"prompt": "What is the current CPU utilization?"}'
agentcore invoke --agent supervisor_agent '{"prompt": "Give me a complete database health report"}'
```

## Tool Reference

### Database Health Tools (14)

| Tool | Description | Source |
|------|-------------|--------|
| `get_database_load` | Database load metrics (AAS) with timeline | Database Insights |
| `get_extended_database_load` | Extended load with instance age awareness | Database Insights |
| `get_wait_events` | Wait event breakdown (CPU, IO, Log, Other) | Database Insights |
| `get_top_sql` | Top SQL queries with actual query text | Database Insights |
| `get_users` | Database users and their load contribution | Database Insights |
| `get_applications` | Application connection patterns | Database Insights |
| `get_database_connections` | Connection count timeline | CloudWatch |
| `get_cpu_utilization` | CPU usage trends | CloudWatch |
| `get_free_storage` | Available storage space | CloudWatch |
| `get_read_write_latency` | Disk I/O latency | CloudWatch |
| `get_iops` | Read/write IOPS | CloudWatch |
| `get_network_throughput` | Network traffic patterns | CloudWatch |
| `get_freeable_memory` | Available memory | CloudWatch |
| `send_email_notification` | Send health alerts | SNS |

### Query Performance Tools (13)

| Tool | Description | Source |
|------|-------------|--------|
| `check_query_store_enabled` | Query Store status and configuration | DMV |
| `get_query_store_top_queries` | Top queries by cpu/duration/io/memory | Query Store |
| `get_query_store_regressed_queries` | Queries that regressed in performance | Query Store |
| `get_query_store_wait_stats` | Wait statistics per query | Query Store |
| `get_query_execution_history` | Query performance timeline (up to 7 days) | Query Store |
| `get_query_store_plan_summary` | Execution plan summary for a query | Query Store |
| `get_slow_queries` | Currently running slow queries | DMV |
| `get_blocking_sessions` | Active blocking chains | DMV |
| `get_query_plan_from_cache` | Execution plan from plan cache | DMV |
| `get_expensive_queries_from_cache` | Top queries since last restart | DMV |
| `suggest_indexes` | Missing index recommendations with CREATE statements | DMV |
| `get_index_usage` | Index usage statistics (unused/expensive) | DMV |
| `send_email_notification` | Send performance alerts | SNS |

### Security Audit Tools (8)

| Tool | Description | Source |
|------|-------------|--------|
| `check_tde_status` | TDE encryption status per database | DMV |
| `check_backup_encryption` | RDS storage and snapshot encryption | RDS API |
| `get_failed_login_attempts` | Failed login attempts (CloudWatch Logs Insights) | CloudWatch Logs |
| `get_rds_events` | RDS event history including config changes | RDS API |
| `get_configuration_changes_from_cloudtrail` | Detailed config changes with who/what/when | CloudTrail |
| `check_rds_security_settings` | Public access, VPC, IAM auth, deletion protection | RDS API |
| `check_rds_audit_settings` | SQL Server Audit (DAS), option groups | RDS API |
| `send_email_notification` | Send security alerts | SNS |

### Data Lifecycle Tools (25)

| Tool | Description | Source |
|------|-------------|--------|
| `get_storage_metrics` | Storage usage and growth trends | CloudWatch |
| `get_iops_trends` | IOPS trends with timeline | CloudWatch |
| `get_throughput_trends` | Read/write throughput trends | CloudWatch |
| `get_latency_trends` | Read/write latency trends | CloudWatch |
| `get_queue_depth_trends` | Disk queue depth (bottleneck indicator) | CloudWatch |
| `analyze_storage_growth` | Growth rate and days until full | CloudWatch |
| `get_storage_configuration` | Storage type, IOPS, throughput config | RDS API |
| `recommend_storage_upgrade` | Analyze metrics and suggest upgrades | RDS API + CloudWatch |
| `get_database_size` | Total database sizes | DMV |
| `get_table_sizes` | Top 20 tables by space | DMV |
| `get_index_sizes` | Top 20 indexes by space | DMV |
| `identify_old_data` | Find archival candidates by date | DMV |
| `get_fragmentation_status` | Index fragmentation >10% | DMV |
| `get_tempdb_size` | TempDB size, used/free per file | DMV |
| `get_tempdb_space_usage_by_session` | TempDB usage by session | DMV |
| `get_tempdb_space_usage_by_query` | TempDB usage by running queries | DMV |
| `get_tempdb_contention` | PFS/SGAM/GAM page latch contention | DMV |
| `get_tempdb_io_stats` | TempDB file I/O latency and stalls | DMV |
| `check_tempdb_file_configuration` | File count, sizes, growth settings | DMV |
| `get_temp_table_usage` | Active temp tables (#temp, ##global) | DMV |
| `get_version_store_usage` | Version store size (row versioning) | DMV |
| `validate_tempdb_configuration` | Best practices check | DMV |
| `analyze_tempdb_bottleneck` | Comprehensive TempDB root cause analysis | DMV |
| `check_backup_status` | Backup retention, recent snapshots | RDS API |
| `send_email_notification` | Send lifecycle alerts | SNS |

### Supervisor Tools (10)

| Tool | Description |
|------|-------------|
| `check_agent_configuration` | Verify all agent ARNs are set |
| `invoke_health_check` | Delegate to Database Health Agent |
| `invoke_performance_analysis` | Delegate to Query Performance Agent |
| `invoke_security_audit` | Delegate to Security Audit Agent |
| `invoke_lifecycle_check` | Delegate to Data Lifecycle Agent |
| `invoke_backup_check` | Delegate to Data Lifecycle Agent (backup only) |
| `invoke_tempdb_analysis` | Delegate to Data Lifecycle Agent (TempDB only) |
| `invoke_custom_agent_query` | Send custom query to any agent |
| `generate_daily_report` | Comprehensive report from all agents |
| `send_email_notification` | Send consolidated alerts |

## Memory

All agents share a single [AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html) instance with two strategies:

- **Semantic Strategy** — Extracts and stores factual findings across sessions for cross-agent knowledge recall
- **Summarization Strategy** — Condenses each session into a summary for efficient context retrieval

All agents connect to the same shared memory using the `MEMORY_ID` environment variable. When `MEMORY_ID` is not set, agents work normally without memory.

## Adding New Tools

1. Add your `@tool` function to the appropriate tools file (e.g., `tools/database_health_tools.py`)
2. Import it in the agent file (e.g., `agents/database_health_agent.py`)
3. Add it to the agent's `_tools` list
4. Redeploy
