# Step-by-Step Setup Guide

This guide breaks down the entire DevOps Agent integration into individual CLI commands. Run each command separately — no scripts required.

> **Prefer the automated approach?** Run `./deploy_gateway.sh` for Step 1, then follow the CLI commands in Steps 2–4 from the [README](README.md).

## Prerequisites

```bash
source ../../.env
source ../../.venv/bin/activate

# Verify required variables
echo "Region: $AWS_REGION"
echo "Subnet: $SUBNET1"
echo "Security Group: $SECURITY_GROUP_ID"
echo "Role: $AGENTCORE_ROLE_ARN"
echo "DB Instance: $DB_INSTANCE_ID"
echo "DB Secret: $DB_SECRET_ID"
echo "SNS Topic: $SNS_TOPIC_NAME"
```

---

## Step 1: Build and Publish the pymssql Lambda Layer

```bash
# Build the layer (Linux x86_64 for Lambda)
pip install pymssql -t /tmp/pymssql-layer/python \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -q

cd /tmp/pymssql-layer && zip -r pymssql-layer-3.12.zip python -q

# Publish to Lambda
export LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name pymssql-layer \
  --compatible-runtimes python3.12 \
  --zip-file fileb:///tmp/pymssql-layer/pymssql-layer-3.12.zip \
  --region $AWS_REGION \
  --query 'LayerVersionArn' --output text)

echo "Layer ARN: $LAYER_ARN"

# Cleanup
rm -rf /tmp/pymssql-layer
```

---

## Step 2: Package Lambda Functions

```bash
cd /path/to/agentic-db-ops  # repo root

TOOLS_DIR=db-engines/sql-server/tools
CONFIG_DIR=db-engines/sql-server/config
GW_DIR=deployment/devops-agent/gateway_tools

# Package health tools
mkdir -p /tmp/health-pkg
cp $GW_DIR/health_handler.py /tmp/health-pkg/lambda_function.py
cp $TOOLS_DIR/database_health_tools.py /tmp/health-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/health-pkg/
cp -r $CONFIG_DIR /tmp/health-pkg/config
cd /tmp/health-pkg && zip -r /tmp/health-tools.zip . -q

# Package query tools
mkdir -p /tmp/query-pkg
cp $GW_DIR/query_handler.py /tmp/query-pkg/lambda_function.py
cp $TOOLS_DIR/query_performance_tools.py /tmp/query-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/query-pkg/
cp -r $CONFIG_DIR /tmp/query-pkg/config
cd /tmp/query-pkg && zip -r /tmp/query-tools.zip . -q
```

---

## Step 3: Deploy Lambda Functions

```bash
export SUBNET2="${SUBNET2:-$SUBNET1}"

# Deploy health tools Lambda
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
  --region $AWS_REGION

# Deploy query tools Lambda
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
  --region $AWS_REGION
```

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

---

## Step 5: Create AgentCore Gateway

```bash
cd deployment/devops-agent
python3 setup_gateway.py
```

This creates:
- Cognito User Pool + App Client (OAuth `client_credentials` grant)
- MCP Gateway with Cognito authorizer
- Registers both Lambda targets with tool schemas
- Outputs `gateway_config.json`

---

## Step 6: Verify Gateway

```bash
python3 agent_gateway.py
```

Ask: `What is the current CPU utilization?`

---

## Step 7: Create Agent Space IAM Roles

```bash
export AWS_ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)

# Agent Space role
aws iam create-role \
  --role-name DevOpsAgentRole-AgentSpace \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

# Operator App role (Web App)
aws iam create-role \
  --role-name DevOpsAgentRole-WebappAdmin \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
```

---

## Step 8: Create Agent Space

```bash
export AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
  --space-name sql-server-dbops \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-AgentSpace \
  --region $AWS_REGION \
  --query 'agentSpaceId' --output text)

echo "Agent Space ID: $AGENT_SPACE_ID"
```

---

## Step 9: Associate AWS Account

```bash
aws devops-agent associate-account \
  --agent-space-id $AGENT_SPACE_ID \
  --account-id $AWS_ACCOUNTID \
  --region $AWS_REGION
```

---

## Step 10: Enable Web App

```bash
aws devops-agent enable-operator-app \
  --agent-space-id $AGENT_SPACE_ID \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-WebappAdmin \
  --region $AWS_REGION
```

---

## Step 11: Register Gateway as MCP Server

```bash
# Load Gateway config
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")
CLIENT_ID=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_secret'])")
TOKEN_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['token_endpoint'])")

# Register
export MCP_SERVICE_ID=$(aws devops-agent register-service \
  --service mcpserver \
  --name "dbops-mcp" \
  --service-details "{\"mcpserver\": {\"name\": \"dbops-mcp\", \"endpoint\": \"$GATEWAY_URL\", \"description\": \"SQL Server diagnostic tools via AgentCore Gateway\", \"authorizationConfig\": {\"oAuthClientCredentials\": {\"clientName\": \"AgentCore-Gateway-OAuth\", \"clientId\": \"$CLIENT_ID\", \"clientSecret\": \"$CLIENT_SECRET\", \"exchangeUrl\": \"$TOKEN_URL\"}}}}" \
  --region $AWS_REGION \
  --query 'serviceId' --output text)

echo "MCP Service ID: $MCP_SERVICE_ID"
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

---

## Step 13: Upload Investigation Skill

```bash
# Zip the skill
cd skills && zip -r sql-server-investigation.zip sql-server-investigation/ && cd ..
```

Then in the AWS Console:
1. Open [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
3. Select `sql-server-investigation.zip`, Agent Type = **Generic**, click **Upload**

---

## Step 14: Start an Investigation

Open the DevOps Agent Web App and try:

```
Give me a complete database health report
```

```
The database is experiencing high CPU. Diagnose the root cause.
```

```
Are there any blocking sessions affecting performance?
```

---

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
aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace

aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

# Delete Gateway
python3 setup_gateway.py --cleanup

# Delete Lambda functions
aws lambda delete-function --function-name dbops-health-tools --region $AWS_REGION
aws lambda delete-function --function-name dbops-query-tools --region $AWS_REGION

# Delete Lambda layer
LAYER_VERSION=$(aws lambda list-layer-versions --layer-name pymssql-layer \
  --region $AWS_REGION --query 'LayerVersions[0].Version' --output text)
aws lambda delete-layer-version --layer-name pymssql-layer \
  --version-number $LAYER_VERSION --region $AWS_REGION
```
