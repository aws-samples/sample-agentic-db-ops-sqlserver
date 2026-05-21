# Step-by-Step Setup Guide

This guide breaks down the entire DevOps Agent integration into individual CLI commands you can run one at a time.

> **Prefer the automated approach?** Run `./deploy_gateway.sh` for Steps 1–5, then follow Steps 7–13 below.

---

## Prerequisites

### IAM Permissions Required

The IAM user or role running these commands needs the following permissions (in addition to the existing `AgentCoreDBOpsRole` used by the agents themselves):

| Permission | Used By |
|-----------|---------|
| `lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:AddPermission`, `lambda:DeleteFunction`, `lambda:GetFunction` | Steps 1–4 (deploy Lambda functions) |
| `lambda:PublishLayerVersion`, `lambda:ListLayerVersions`, `lambda:DeleteLayerVersion` | Step 1 (pymssql layer) |
| `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:DetachRolePolicy`, `iam:DeleteRole`, `iam:PassRole` | Step 7 (DevOps Agent IAM roles) |
| `cognito-idp:CreateUserPool`, `cognito-idp:CreateUserPoolClient`, `cognito-idp:DeleteUserPool` | Step 5 (OAuth authorizer via SDK) |
| `bedrock-agentcore:CreateMcpGateway`, `bedrock-agentcore:CreateMcpGatewayTarget`, `bedrock-agentcore:DeleteMcpGateway` | Step 5 (Gateway creation via SDK) |
| `devops-agent:CreateAgentSpace`, `devops-agent:DeleteAgentSpace`, `devops-agent:AssociateAccount`, `devops-agent:EnableOperatorApp`, `devops-agent:RegisterService`, `devops-agent:DeregisterService`, `devops-agent:AssociateService`, `devops-agent:DisassociateService`, `devops-agent:GetAgentSpace`, `devops-agent:ListAssociations` | Steps 8–12 (DevOps Agent setup) |
| `sts:GetCallerIdentity` | Prerequisites (get account ID) |

### Environment Setup

```bash
# Navigate to this directory (all commands assume you're here)
cd deployment/devops-agent

# Load environment
source ../../.env
source ../../.venv/bin/activate

# Install additional dependencies for Gateway client
pip install bedrock-agentcore-starter-toolkit mcp strands-agents strands-agents-tools -q

# Verify required variables are set
for var in AWS_REGION SUBNET1 SECURITY_GROUP_ID AGENTCORE_ROLE_ARN DB_SECRET_ID DB_INSTANCE_ID SNS_TOPIC_NAME; do
  echo "$var=${!var:?ERROR: $var is not set}"
done

# Get account ID (used in later steps)
export AWS_ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)
echo "Account: $AWS_ACCOUNTID"
```

All commands below assume you remain in `deployment/devops-agent/`.

---

## Step 1: Build and Publish the pymssql Lambda Layer

```bash
pip install pymssql -t /tmp/pymssql-layer/python \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -q

cd /tmp/pymssql-layer && zip -r pymssql-layer-3.12.zip python -q && cd -

export LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name pymssql-layer \
  --compatible-runtimes python3.12 \
  --zip-file fileb:///tmp/pymssql-layer/pymssql-layer-3.12.zip \
  --region $AWS_REGION \
  --query 'LayerVersionArn' --output text)

echo "✅ Layer ARN: $LAYER_ARN"
rm -rf /tmp/pymssql-layer
```

---

## Step 2: Package Lambda Functions

```bash
TOOLS_DIR=../../db-engines/sql-server/tools
CONFIG_DIR=../../db-engines/sql-server/config

# Health tools
rm -rf /tmp/health-pkg && mkdir -p /tmp/health-pkg
cp gateway_tools/health_handler.py /tmp/health-pkg/lambda_function.py
cp $TOOLS_DIR/database_health_tools.py /tmp/health-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/health-pkg/
cp -r $CONFIG_DIR /tmp/health-pkg/config
cd /tmp/health-pkg && zip -r /tmp/health-tools.zip . -q && cd -

# Query tools
rm -rf /tmp/query-pkg && mkdir -p /tmp/query-pkg
cp gateway_tools/query_handler.py /tmp/query-pkg/lambda_function.py
cp $TOOLS_DIR/query_performance_tools.py /tmp/query-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/query-pkg/
cp -r $CONFIG_DIR /tmp/query-pkg/config
cd /tmp/query-pkg && zip -r /tmp/query-tools.zip . -q && cd -

echo "✅ /tmp/health-tools.zip"
echo "✅ /tmp/query-tools.zip"
```

---

## Step 3: Deploy Lambda Functions

```bash
export SUBNET2="${SUBNET2:-$SUBNET1}"

# Health tools Lambda
aws lambda create-function \
  --function-name dbops-health-tools \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role $AGENTCORE_ROLE_ARN \
  --zip-file fileb:///tmp/health-tools.zip \
  --layers $LAYER_ARN \
  --timeout 60 \
  --memory-size 256 \
  --vpc-config SubnetIds=$SUBNET1,$SUBNET2,SecurityGroupIds=$SECURITY_GROUP_ID \
  --environment "Variables={DB_INSTANCE_ID=$DB_INSTANCE_ID,DB_SECRET_ID=$DB_SECRET_ID,AWS_REGION_NAME=$AWS_REGION,SNS_TOPIC_NAME=$SNS_TOPIC_NAME}" \
  --region $AWS_REGION \
  --query 'FunctionArn' --output text

# Query tools Lambda
aws lambda create-function \
  --function-name dbops-query-tools \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role $AGENTCORE_ROLE_ARN \
  --zip-file fileb:///tmp/query-tools.zip \
  --layers $LAYER_ARN \
  --timeout 60 \
  --memory-size 256 \
  --vpc-config SubnetIds=$SUBNET1,$SUBNET2,SecurityGroupIds=$SECURITY_GROUP_ID \
  --environment "Variables={DB_INSTANCE_ID=$DB_INSTANCE_ID,DB_SECRET_ID=$DB_SECRET_ID,AWS_REGION_NAME=$AWS_REGION,SNS_TOPIC_NAME=$SNS_TOPIC_NAME}" \
  --region $AWS_REGION \
  --query 'FunctionArn' --output text

# Cleanup temp files
rm -rf /tmp/health-pkg /tmp/query-pkg /tmp/health-tools.zip /tmp/query-tools.zip
```

Expected output: two Lambda ARNs like `arn:aws:lambda:us-west-2:123456789012:function:dbops-health-tools`

---

## Step 4: Grant Gateway Invoke Permissions

```bash
aws lambda add-permission \
  --function-name dbops-health-tools \
  --statement-id agentcore-gateway-invoke \
  --action lambda:InvokeFunction \
  --principal bedrock-agentcore.amazonaws.com \
  --region $AWS_REGION

aws lambda add-permission \
  --function-name dbops-query-tools \
  --statement-id agentcore-gateway-invoke \
  --action lambda:InvokeFunction \
  --principal bedrock-agentcore.amazonaws.com \
  --region $AWS_REGION
```

Expected output: `"Statement"` JSON confirming the permission was added.

---

## Step 5: Create AgentCore Gateway

This uses the `bedrock-agentcore-starter-toolkit` SDK to create a Cognito OAuth authorizer, the MCP Gateway, and register both Lambda targets with their tool schemas.

```bash
python3 setup_gateway.py
```

Expected output:
```
  Creating Cognito OAuth authorizer...
  ✅ Cognito authorizer created
  Creating MCP Gateway...
  ✅ Gateway created: https://gw-xxx.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp
  Registering dbops-health-tools target (14 tools)...
  ✅ Health tools registered
  Registering dbops-query-tools target (13 tools)...
  ✅ Query tools registered
  ✅ Configuration saved to gateway_config.json
```

> **What `setup_gateway.py` does internally:**
> 1. `GatewayClient.create_oauth_authorizer_with_cognito()` — creates Cognito User Pool + App Client
> 2. `GatewayClient.create_mcp_gateway()` — creates the Gateway with Cognito authorizer
> 3. `GatewayClient.create_mcp_gateway_target()` × 2 — registers each Lambda with tool schemas
> 4. Saves Gateway URL + OAuth credentials to `gateway_config.json`

---

## Step 6: Verify Gateway Works

```bash
python3 agent_gateway.py
```

Ask: `What is the current CPU utilization?` — you should get a metric response. Type `exit` to quit.

> **Note:** First invocation may take 10–15 seconds (Lambda cold start + VPC ENI attachment).

---

## Step 7: Create Agent Space IAM Roles

```bash
# Agent Space role (allows DevOps Agent to access AWS resources)
aws iam create-role \
  --role-name DevOpsAgentRole-AgentSpace \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

# Operator App role (enables the browser-based Web App)
aws iam create-role \
  --role-name DevOpsAgentRole-WebappAdmin \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
```

Expected output: role ARN JSON for each `create-role` call.

---

## Step 8: Create Agent Space

```bash
export AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
  --space-name sql-server-dbops \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-AgentSpace \
  --region $AWS_REGION \
  --query 'agentSpaceId' --output text)

echo "✅ Agent Space ID: $AGENT_SPACE_ID"
```

---

## Step 9: Associate AWS Account

```bash
aws devops-agent associate-account \
  --agent-space-id $AGENT_SPACE_ID \
  --account-id $AWS_ACCOUNTID \
  --region $AWS_REGION
```

This enables topology discovery — DevOps Agent can see your AWS resources.

---

## Step 10: Enable Web App

```bash
aws devops-agent enable-operator-app \
  --agent-space-id $AGENT_SPACE_ID \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-WebappAdmin \
  --region $AWS_REGION
```

You can now access the DevOps Agent Web App from the AWS Console.

---

## Step 11: Register Gateway as MCP Server

```bash
# Read connection details from gateway_config.json
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")
CLIENT_ID=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_secret'])")
TOKEN_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['token_endpoint'])")

echo "Gateway: $GATEWAY_URL"
echo "Client ID: $CLIENT_ID"
echo "Token URL: $TOKEN_URL"

# Register as MCP server capability provider
export MCP_SERVICE_ID=$(aws devops-agent register-service \
  --service mcpserver \
  --name "dbops-mcp" \
  --service-details "{\"mcpserver\": {\"name\": \"dbops-mcp\", \"endpoint\": \"$GATEWAY_URL\", \"description\": \"SQL Server diagnostic tools via AgentCore Gateway\", \"authorizationConfig\": {\"oAuthClientCredentials\": {\"clientName\": \"AgentCore-Gateway-OAuth\", \"clientId\": \"$CLIENT_ID\", \"clientSecret\": \"$CLIENT_SECRET\", \"exchangeUrl\": \"$TOKEN_URL\"}}}}" \
  --region $AWS_REGION \
  --query 'serviceId' --output text)

echo "✅ MCP Service ID: $MCP_SERVICE_ID"
```

---

## Step 12: Allowlist Tools in Agent Space

```bash
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --configuration '{"mcpserver": {"tools": ["dbops-health-tools___get_applications", "dbops-health-tools___get_cpu_utilization", "dbops-health-tools___get_database_connections", "dbops-health-tools___get_database_load", "dbops-health-tools___get_extended_database_load", "dbops-health-tools___get_free_storage", "dbops-health-tools___get_freeable_memory", "dbops-health-tools___get_iops", "dbops-health-tools___get_network_throughput", "dbops-health-tools___get_read_write_latency", "dbops-health-tools___get_top_sql", "dbops-health-tools___get_users", "dbops-health-tools___get_wait_events", "dbops-health-tools___send_email_notification", "dbops-query-tools___check_query_store_enabled", "dbops-query-tools___get_blocking_sessions", "dbops-query-tools___get_expensive_queries_from_cache", "dbops-query-tools___get_index_usage", "dbops-query-tools___get_query_execution_history", "dbops-query-tools___get_query_plan_from_cache", "dbops-query-tools___get_query_store_plan_summary", "dbops-query-tools___get_query_store_regressed_queries", "dbops-query-tools___get_query_store_top_queries", "dbops-query-tools___get_query_store_wait_stats", "dbops-query-tools___get_slow_queries", "dbops-query-tools___send_email_notification", "dbops-query-tools___suggest_indexes"]}}' \
  --region $AWS_REGION
```

This makes all 27 tools available to the DevOps Agent. Tool names use the format `<target>___<tool>` (triple underscore).

---

## Step 13: Upload Investigation Skill

```bash
cd skills && zip -r ../sql-server-investigation.zip sql-server-investigation/ -q && cd ..
echo "✅ sql-server-investigation.zip created"
```

Then upload via the AWS Console:
1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
3. Select `sql-server-investigation.zip`, set Agent Type to **Generic**, click **Upload**
4. Verify the skill shows **Active** status

---

## Step 14: Start an Investigation

Open the DevOps Agent Web App (from Step 10) and try:

```
Give me a complete database health report
```

```
The database is experiencing high CPU. Diagnose the root cause.
```

```
Are there any blocking sessions affecting performance?
```

The agent follows the skill methodology: triage → diagnose → drill down → correlate → recommend.

---

## Cleanup

Run these in reverse order to tear everything down:

```bash
# Remove MCP server from Agent Space
aws devops-agent disassociate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --region $AWS_REGION

# Deregister MCP server
aws devops-agent deregister-service \
  --service-id $MCP_SERVICE_ID \
  --region $AWS_REGION

# Delete Agent Space
aws devops-agent delete-agent-space \
  --agent-space-id $AGENT_SPACE_ID \
  --region $AWS_REGION

# Delete IAM roles
aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace

aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

# Delete Gateway + Cognito
python3 setup_gateway.py --cleanup

# Delete Lambda functions
aws lambda delete-function --function-name dbops-health-tools --region $AWS_REGION
aws lambda delete-function --function-name dbops-query-tools --region $AWS_REGION

# Delete Lambda layer
LAYER_VERSION=$(aws lambda list-layer-versions --layer-name pymssql-layer \
  --region $AWS_REGION --query 'LayerVersions[0].Version' --output text)
aws lambda delete-layer-version --layer-name pymssql-layer \
  --version-number $LAYER_VERSION --region $AWS_REGION

# Remove generated files
rm -f gateway_config.json sql-server-investigation.zip
```
