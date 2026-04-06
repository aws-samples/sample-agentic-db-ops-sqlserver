# SQL Server Tools

`@tool` decorated functions grouped by agent domain. Each file is self-contained with its own imports and helpers (e.g., `get_db_connection()`). Configuration is imported from `config/settings.py`.

| File | Tools | Data Sources |
|------|-------|-------------|
| `database_health_tools.py` | 14 | Database Insights, CloudWatch, SNS |
| `query_performance_tools.py` | 13 | SQL Server DMVs, Query Store, SNS |
| `security_audit_tools.py` | 8 | RDS API, CloudWatch Logs, CloudTrail, DMVs, SNS |
| `data_lifecycle_tools.py` | 25 | CloudWatch, DMVs, RDS API, SNS |
| `supervisor_tools.py` | 10 | AgentCore A2A invocation, SNS |

**Total: 70 tools across 5 files**

## Adding a New Tool

1. Add your `@tool` function to the appropriate tools file
2. Import it in the corresponding agent file in `agents/`
3. Add it to the agent's `_tools` list
4. Redeploy
