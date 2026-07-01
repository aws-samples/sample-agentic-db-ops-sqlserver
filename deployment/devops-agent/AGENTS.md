Agent Type: Investigation (INCIDENT_RCA)

# Investigation Agent Instructions

## SQL Server Investigations

When investigating issues involving SQL Server or RDS SQL Server instances, always
use the `sql-server-investigation` skill.

### Triggers

Apply this skill when the investigation involves any of the following:

- SQL Server or MSSQL database instances
- RDS SQL Server (any edition)
- High CPU, query timeouts, or performance issues on SQL Server
- Blocking, deadlocks, or lock contention
- Query performance degradation or regressions

### Why

The `sql-server-investigation` skill provides SQL Server-specific diagnostic
capabilities including:

- DMV analysis (`sys.dm_exec_requests`, `sys.dm_tran_locks`, `sys.dm_os_waiting_tasks`)
- Blocking chain identification
- Wait event interpretation (LCK_M_IX, LCK_M_X, LCK_M_S, CXPACKET, etc.)
- Query Store and execution plan analysis
- Extended Events (XEL) file parsing

These capabilities go beyond generic AWS observability tools and provide deeper root
cause analysis for SQL Server-specific issues.
