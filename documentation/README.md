# Documentation

## Overview

Autonomous DBOps is a multi-agent system that converts SQL Server diagnostic expertise into AI agents that run autonomously on Amazon Bedrock AgentCore. Five specialized agents collaborate through a supervisor pattern, sharing knowledge through a common memory layer.

## Design Principles

- **Separation of concerns** — Each agent owns a specific domain (health, performance, security, lifecycle). No tool overlap between agents.
- **Thin agents, rich tools** — Agent files are lightweight (imports + system prompt + entrypoint). All logic lives in `@tool` functions.
- **Shared memory, independent execution** — Agents run in isolated containers but share a single memory resource for cross-session knowledge.
- **Private networking** — All agents run in private subnets. AWS service access is through VPC endpoints only.
- **Least-privilege IAM** — Scoped permissions per service, no wildcard actions.

## System Architecture

```
                                    ┌─────────────────────────────────────────────────────────────────┐
                                    │                        VPC (Private Subnets)                    │
                                    │                                                                 │
┌──────────────┐                    │  ┌───────────────────────────────────────────────────────────┐  │
│              │  agentcore /       │  │              Amazon Bedrock AgentCore Runtime              │  │
│  DBA /       │  boto3 API        │  │                                                           │  │
│  Operator    │───────────────────►│  │  ┌─────────────────────────────────────────────────────┐  │  │
│              │                    │  │  │              🎯 Supervisor Agent                     │  │  │
│  (CLI /      │◄───────────────────│  │  │         Routes queries, correlates findings          │  │  │
│   Kiro IDE)  │   streaming        │  │  └──────────┬──────────┬──────────┬──────────┬──────────┘  │  │
└──────────────┘   response         │  │             │          │          │          │             │  │
                                    │  │        A2A  ▼     A2A  ▼     A2A  ▼     A2A  ▼            │  │
                                    │  │  ┌──────────┐ ┌────────┐ ┌───────┐ ┌──────────────────┐   │  │
                                    │  │  │📊 Health │ │⚡ Query│ │🔒 Sec │ │💾 Data Lifecycle │    │  │
                                    │  │  │  Agent   │ │  Perf  │ │ Audit │ │     Agent        │   │  │
                                    │  │  │ 14 tools │ │13 tools│ │8 tools│ │    25 tools      │   │  │
                                    │  │  └────┬─────┘ └───┬────┘ └───┬───┘ └────────┬─────────┘   │  │
                                    │  └───────┼───────────┼──────────┼──────────────┼──────────────┘ │
                                    │          │           │          │              │                │
                                    │  ┌───────▼───────────▼──────────▼──────────────▼──────────────┐  │
                                    │  │                  🧠 AgentCore Memory                       │  │
                                    │  │          Semantic Strategy + Summarization Strategy         │  │
                                    │  └───────────────────────────────────────────────────────────┘  │
                                    │                                                                 │
                                    │  ┌───────────────────────────────────────────────────────────┐  │
                                    │  │                    VPC Endpoints (16 services)             │  │
                                    │  └──────────┬────────────────────────────────────┬────────────┘  │
                                    └─────────────┼────────────────────────────────────┼───────────────┘
                                                  ▼                                    ▼
                              ┌────────────────────────────────┐    ┌──────────────────────────────────┐
                              │  Amazon RDS for SQL Server      │    │  AWS Services                     │
                              │  • DMVs • Query Store • TempDB  │    │  Bedrock, CloudWatch, PI,         │
                              │  • Secrets Manager (credentials)│    │  CloudTrail, SNS, KMS             │
                              └────────────────────────────────┘    └──────────────────────────────────┘
```

## Agent Communication Pattern

The Supervisor Agent uses **Agent-to-Agent (A2A)** invocation via `bedrock-agentcore:InvokeAgentRuntime`. This is not HTTP — it's a direct AgentCore Runtime API call.

```
User: "Why is the database slow?"
  │
  ▼
Supervisor Agent
  ├── invoke_health_check()      → Database Health Agent → returns CPU, memory, load, waits
  ├── invoke_performance_analysis() → Query Performance Agent → returns slow queries, blocking
  │
  ▼
Supervisor correlates: "CPU at 87% caused by query ID 4521 doing full table scans"
```

The Supervisor decides which agents to call based on the question. It can call multiple agents in sequence and correlate their findings.

## Tool Execution Flow

Each `@tool` function follows this pattern:

```
Agent receives prompt
  │
  ▼
Claude (Bedrock) selects tool based on system prompt + tool descriptions
  │
  ▼
@tool function executes (boto3 API call or pymssql query)
  │
  ▼
Tool returns Dict[str, Any] result
  │
  ▼
Claude analyzes result, decides: call another tool or respond
  │
  ▼
Final response returned to caller
```

Tools connect to data sources in two ways:
- **AWS APIs** (via VPC endpoints): CloudWatch, Database Insights, RDS, CloudTrail, SNS
- **Direct SQL** (via pymssql): DMVs, Query Store, TempDB — credentials from Secrets Manager

## Memory Architecture

All 5 agents share a single AgentCore Memory resource with two strategies:

```
┌──────────────────────────────────────────────────────────┐
│                    AgentCore Memory                       │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Semantic Strategy (dbops_facts)                   │  │
│  │  - Extracts facts from conversations               │  │
│  │  - "CPU reached 87% at 14:30 UTC on 2026-03-16"   │  │
│  │  - "Missing index on Orders.CustomerID"            │  │
│  │  - Retrieval: top_k=5, relevance_score=0.3         │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Summarization Strategy (dbops_summaries)          │  │
│  │  - Summarizes conversation sessions                │  │
│  │  - "Health check found high CPU and IO waits"      │  │
│  │  - Retrieval: top_k=3, relevance_score=0.3         │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  Event expiry: 365 days                                   │
└──────────────────────────────────────────────────────────┘
```

**Cross-agent knowledge flow:**
1. Health Agent runs, finds CPU at 87% → stored as semantic fact
2. Query Performance Agent runs, finds blocking query → stored as semantic fact
3. Supervisor Agent asked "what happened today?" → retrieves both facts from memory without re-running tools

## Networking

Agents run in private subnets with no NAT gateway or internet access. All AWS service communication goes through VPC endpoints.

### Required VPC Endpoints

| Type | Service | Used By |
|------|---------|---------|
| Gateway | S3 | ECR image layers |
| Interface | `bedrock-runtime` | All agents (LLM) |
| Interface | `bedrock-agentcore` | All agents (runtime + A2A) |
| Interface | `bedrock-agentcore-control` | All agents (control plane communication) |
| Interface | `bedrock-agentcore.gateway` | All agents (invocation routing) |
| Interface | `secretsmanager` | Query Perf, Security, Lifecycle |
| Interface | `rds` | Health, Security, Lifecycle |
| Interface | `monitoring` | Health, Lifecycle (CloudWatch) |
| Interface | `logs` | All agents (agent logging) + Security (CW Logs Insights) |
| Interface | `ecr.dkr` + `ecr.api` | All agents (container pull) |

### Recommended VPC Endpoints

| Type | Service | Used By |
|------|---------|---------|
| Interface | `pi` | Database Health (Database Insights) |
| Interface | `sns` | All agents (notifications) |
| Interface | `cloudtrail` | Security Audit |
| Interface | `kms` | Database Health (decrypt PI data) |
| Interface | `sts` | Credential refresh + cross-account |

## Code Structure

```
db-engines/sql-server/
├── config/settings.py              ← Environment variables only (no logic)
├── tools/
│   ├── database_health_tools.py    ← 14 @tool functions + helpers (PI client, period calc)
│   ├── query_performance_tools.py  ← 13 @tool functions + helpers (DB connection)
│   ├── security_audit_tools.py     ← 8 @tool functions + helpers (DB connection)
│   ├── data_lifecycle_tools.py     ← 25 @tool functions + helpers (DB connection, period calc)
│   └── supervisor_tools.py         ← 10 @tool functions + A2A helper
├── agents/
│   ├── database_health_agent.py    ← imports + system prompt + Agent + entrypoint
│   ├── query_performance_agent.py
│   ├── security_audit_agent.py
│   ├── data_lifecycle_agent.py
│   └── supervisor_agent.py
└── requirements.txt
```

Each tools file is self-contained — it imports only from `config.settings` and has its own helpers (e.g., `get_db_connection()`). This means tools files can be tested independently.

Each agent file is thin (~4-5 KB) — it imports tools, defines a system prompt, creates the `Agent`, and wires up the AgentCore entrypoint with optional memory.

## IAM

Two roles are required. See [templates/README.md](../templates/README.md) for setup.

| Role | Trusted By | Purpose |
|------|-----------|---------|
| AgentCore Execution Role | `bedrock-agentcore.amazonaws.com` | Agents call AWS services |
| Operator Role | Your IAM user / instance | Deploy and invoke agents |
