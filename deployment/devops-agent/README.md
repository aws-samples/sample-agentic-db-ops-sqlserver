# AWS DevOps Agent Integration

Connect your SQL Server diagnostic tools to [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html) for managed, zero-code investigations through a web interface. This is an alternative to invoking the agents directly on AgentCore Runtime (`agentcore invoke`) — the same health and query capabilities, surfaced in a managed web app instead of the CLI.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  DevOps Agent   │────▶│ AgentCore Gateway │────▶│  Lambda Functions   │
│  (Web App)      │     │  (MCP endpoint)   │     │  (your tools)       │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
        │                        │                         │
   Skills guide          IAM auth + routing         CloudWatch, DMVs,
   methodology            (SigV4)                  Database Insights
```

1. Your existing tools (health + query) are packaged as Lambda functions
2. AgentCore Gateway exposes them as MCP endpoints with AWS IAM (SigV4) authentication
3. DevOps Agent connects to the Gateway and discovers all 27 tools
4. An investigation skill teaches the agent your structured troubleshooting methodology

## Prerequisites

- `deployment/agentcore/deploy.sh` completed (5 agents running on AgentCore Runtime)
- `.env` sourced with all environment variables
- Python 3.12+
- `bedrock-agentcore-starter-toolkit` installed

## Step 1: Deploy the Gateway

This packages your health and query tools as Lambda functions, creates the
authorizer, and registers everything with AgentCore Gateway.

```bash
cd deployment/devops-agent
chmod +x deploy_gateway.sh
./deploy_gateway.sh
```

This creates `gateway_config.json` with the Gateway URL.

> **Prefer to run each step by hand?** `deploy_gateway.sh` automates the gateway
> setup. For the full manual, step-by-step walkthrough of what it does (IAM policy,
> publishing the pymssql layer, packaging and creating each Lambda, creating the
> gateway, and registering targets), see [SETUP.md](SETUP.md).

### Verify Gateway

```bash
python3 agent_gateway.py
```

Ask: "What is the current CPU utilization?" — confirms tools work end-to-end via MCP.

## Step 2: Create the Agent Space

Create the Agent Space IAM roles, the Agent Space itself, associate your AWS
account, and enable the Web App. These steps are documented in detail in
[SETUP.md](SETUP.md) — see:

- **Step 8 — Create Agent Space IAM Roles**
- **Step 9 — Create Agent Space**
- **Step 10 — Associate AWS Account**
- **Step 11 — Enable Web App**

> Run them from `deployment/devops-agent/` with `.env` sourced (so `$AWS_REGION`,
> `$AWS_ACCOUNTID`, and `$AGENTCORE_ROLE_ARN` are set). They export
> `$AGENT_SPACE_ID`, which the next step uses.

## Step 3: Connect Gateway as MCP Server

Register the AgentCore Gateway (deployed in Step 1) as an MCP server on the Agent
Space and allowlist all 27 tools. The gateway uses AWS IAM (SigV4) auth. These
steps are documented in detail in [SETUP.md](SETUP.md) — see:

- **Step 12 — Register Gateway as MCP Server**
- **Step 13 — Allowlist Tools**

> These read `gateway_config.json` (from Step 1) for the Gateway URL and use
> `$AGENT_SPACE_ID` (from Step 2) and `$AGENTCORE_ROLE_ARN`.

## Step 4: Upload Investigation Skill

The skill teaches DevOps Agent a structured troubleshooting methodology: triage → diagnose → drill down → correlate → recommend.

1. Zip the skill:
   ```bash
   cd skills && zip -r ../sql-server-investigation.zip sql-server-investigation/ && cd ..
   ```
2. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
3. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
4. Select `sql-server-investigation.zip`, set Agent Type to **Generic**, click **Upload**

## Use It

Open the DevOps Agent Web App and start an investigation:

```
"Give me a complete database health report"
"The database is experiencing high CPU. Diagnose the root cause."
"Are there any blocking sessions affecting performance?"
```

The agent follows the skill methodology — triaging health, identifying bottleneck type via wait events, drilling into the specific issue, and producing severity-rated recommendations.

## Tool Reference

| Gateway Target | Tools | Data Sources |
|---------------|-------|-------------|
| `dbops-health-tools` (14) | CPU, memory, connections, load, wait events, IOPS, latency, storage | CloudWatch, Database Insights |
| `dbops-query-tools` (13) | Slow queries, blocking, Query Store, indexes, execution plans | SQL Server DMVs |

Tool names in DevOps Agent use the format: `<target>___<tool>` (triple underscore).

> **Note:** `dbops-health-tools` overlaps with metrics the DevOps Agent can read
> natively (CloudWatch, Performance Insights / Database Insights). The
> `sql-server-investigation` skill deliberately prefers the agent's native API
> access for triage and uses these health tools only as a fallback, reserving the
> MCP/Lambda path for the SQL-level detail in `dbops-query-tools`. See the skill's
> "Data Source Boundaries" section for the rationale.

## Cleanup

Tear down in this order. (For the authoritative, fully-detailed teardown — including
every variable lookup — see the **Cleanup** section of [SETUP.md](SETUP.md).)

```bash
# 1. Disassociate the MCP service (disassociate takes the ASSOCIATION id, not the service id)
ASSOCIATION_ID=$(aws devops-agent list-associations --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION \
  --query "associations[?serviceId=='$MCP_SERVICE_ID'].associationId | [0]" --output text)
aws devops-agent disassociate-service --agent-space-id $AGENT_SPACE_ID --association-id $ASSOCIATION_ID --region $AWS_REGION

# 2. Deregister the MCP service, then delete the Agent Space
aws devops-agent deregister-service --service-id $MCP_SERVICE_ID --region $AWS_REGION
aws devops-agent delete-agent-space --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION

# 3. Delete the Agent Space IAM roles
aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace
aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

# 4. Delete the Gateway, Lambdas, and pymssql layer (run from this directory)
./deploy_gateway.sh --cleanup

# 5. (Optional) Remove the gateway-specific grants added to the SHARED execution role.
#    Do NOT delete AgentCoreDBOpsRole itself — the 5 AgentCore agents use it.
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name InvokeDbopsGateway 2>/dev/null || true
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name GatewayInvokeDbopsLambdas 2>/dev/null || true
```
