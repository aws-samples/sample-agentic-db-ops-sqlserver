# AgentCore Deployment

Deploy all 5 SQL Server agents to [Amazon Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) with shared memory, VPC networking, and auto-scaling.

## Prerequisites

1. **AWS account** with Bedrock model access (Claude Sonnet) and an RDS SQL Server instance
2. **AgentCore Starter Toolkit** installed:
   ```bash
   pip install bedrock-agentcore-starter-toolkit
   ```
3. **Environment variables** configured in `.env` at the repo root — see the main [README](../../README.md) for setup
4. **VPC endpoints** configured — see [config/README.md](../../db-engines/sql-server/config/README.md) for the full list

## Deploy

From the repo root:

```bash
./deploy.sh
```

This script:
1. Creates shared AgentCore Memory (semantic + summarization strategies, 365-day event expiry)
2. Stages the modular code (agents + tools + config) into a flat deployment directory
3. Deploys 4 sub-agents with VPC networking and environment variables
4. Resolves sub-agent ARNs and deploys the Supervisor Agent with A2A configuration
5. Validates all 5 agents are READY

## Cleanup

From the repo root:

```bash
source .env && source .venv/bin/activate
python3 scripts/cleanup_agents.py
```

## Files

| File | Description |
|------|-------------|
| `deploy.sh` | Thin wrapper (actual deploy script is at repo root: `./deploy.sh`) |
| `cleanup.sh` | Thin wrapper (actual cleanup is `scripts/cleanup_agents.py`) |
