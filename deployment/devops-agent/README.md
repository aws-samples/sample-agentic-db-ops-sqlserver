# AWS DevOps Agent Integration

Connect your SQL Server diagnostic tools to [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html) for managed, zero-code investigations through a web interface.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  DevOps Agent   │────▶│ AgentCore Gateway │────▶│  Lambda Functions   │
│  (Web App)      │     │  (MCP endpoint)   │     │  (your tools)       │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
        │                        │                         │
   Skills guide            OAuth + routing          CloudWatch, DMVs,
   methodology             (Cognito)               Database Insights
```

1. Your existing tools (health + query) are packaged as Lambda functions
2. AgentCore Gateway exposes them as MCP endpoints with OAuth authentication
3. DevOps Agent connects to the Gateway and discovers all 27 tools
4. An investigation skill teaches the agent your structured troubleshooting methodology

## Prerequisites

- `deployment/agentcore/deploy.sh` completed (5 agents running on AgentCore Runtime)
- `.env` sourced with all environment variables
- Python 3.12+
- `bedrock-agentcore-starter-toolkit` installed

## Step 1: Deploy the Gateway

This packages your health and query tools as Lambda functions, creates a Cognito OAuth authorizer, and registers everything with AgentCore Gateway.

```bash
cd deployment/devops-agent
chmod +x deploy_gateway.sh
./deploy_gateway.sh
```

This creates `gateway_config.json` with the Gateway URL and OAuth credentials.

### Verify Gateway

```bash
python3 agent_gateway.py
```

Ask: "What is the current CPU utilization?" — confirms tools work end-to-end via MCP.

## Step 2: Create the Agent Space

```bash
export AWS_ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)

# Create Agent Space IAM role
aws iam create-role \
  --role-name DevOpsAgentRole-AgentSpace \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --region $AWS_REGION

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

# Create Operator App IAM role (enables Web App)
aws iam create-role \
  --role-name DevOpsAgentRole-WebappAdmin \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --region $AWS_REGION

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy

# Create Agent Space
export AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
  --space-name sql-server-dbops \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-AgentSpace \
  --region $AWS_REGION \
  --query 'agentSpaceId' --output text)

echo "Agent Space ID: $AGENT_SPACE_ID"

# Associate your AWS account
aws devops-agent associate-account \
  --agent-space-id $AGENT_SPACE_ID \
  --account-id $AWS_ACCOUNTID \
  --region $AWS_REGION

# Enable the Web App
aws devops-agent enable-operator-app \
  --agent-space-id $AGENT_SPACE_ID \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-WebappAdmin \
  --region $AWS_REGION
```

## Step 3: Connect Gateway as MCP Server

```bash
# Load Gateway config
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")
CLIENT_ID=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_secret'])")
TOKEN_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['token_endpoint'])")

# Register MCP server
export MCP_SERVICE_ID=$(aws devops-agent register-service \
  --service mcpserver \
  --name "dbops-mcp" \
  --service-details "{\"mcpserver\": {\"name\": \"dbops-mcp\", \"endpoint\": \"$GATEWAY_URL\", \"description\": \"SQL Server diagnostic tools via AgentCore Gateway\", \"authorizationConfig\": {\"oAuthClientCredentials\": {\"clientName\": \"AgentCore-Gateway-OAuth\", \"clientId\": \"$CLIENT_ID\", \"clientSecret\": \"$CLIENT_SECRET\", \"exchangeUrl\": \"$TOKEN_URL\"}}}}" \
  --region $AWS_REGION \
  --query 'serviceId' --output text)

echo "MCP Service ID: $MCP_SERVICE_ID"

# Associate with Agent Space and allowlist all 27 tools
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --configuration '{"mcpserver": {"tools": ["dbops-health-tools___get_applications", "dbops-health-tools___get_cpu_utilization", "dbops-health-tools___get_database_connections", "dbops-health-tools___get_database_load", "dbops-health-tools___get_extended_database_load", "dbops-health-tools___get_free_storage", "dbops-health-tools___get_freeable_memory", "dbops-health-tools___get_iops", "dbops-health-tools___get_network_throughput", "dbops-health-tools___get_read_write_latency", "dbops-health-tools___get_top_sql", "dbops-health-tools___get_users", "dbops-health-tools___get_wait_events", "dbops-health-tools___send_email_notification", "dbops-query-tools___check_query_store_enabled", "dbops-query-tools___get_blocking_sessions", "dbops-query-tools___get_expensive_queries_from_cache", "dbops-query-tools___get_index_usage", "dbops-query-tools___get_query_execution_history", "dbops-query-tools___get_query_plan_from_cache", "dbops-query-tools___get_query_store_plan_summary", "dbops-query-tools___get_query_store_regressed_queries", "dbops-query-tools___get_query_store_top_queries", "dbops-query-tools___get_query_store_wait_stats", "dbops-query-tools___get_slow_queries", "dbops-query-tools___send_email_notification", "dbops-query-tools___suggest_indexes"]}}' \
  --region $AWS_REGION
```

## Step 4: Upload Investigation Skill

The skill teaches DevOps Agent a structured troubleshooting methodology: triage → diagnose → drill down → correlate → recommend.

1. Zip the skill:
   ```bash
   cd skills && zip -r sql-server-investigation.zip sql-server-investigation/ && cd ..
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

## Cleanup

```bash
# Remove MCP server association
aws devops-agent disassociate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --region $AWS_REGION

# Delete Agent Space
aws devops-agent delete-agent-space \
  --agent-space-id $AGENT_SPACE_ID \
  --region $AWS_REGION

# Delete IAM roles
aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace
aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

# Delete Gateway (run from this directory)
./deploy_gateway.sh --cleanup
```
