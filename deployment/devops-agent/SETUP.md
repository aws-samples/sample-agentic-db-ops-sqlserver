# Setup Guide

Connect your SQL Server diagnostic tools to AWS DevOps Agent for managed, zero-code investigations.

---

## Prerequisites

### IAM Permissions

Create a policy with these permissions and attach it to your operator role before starting:

```bash
aws iam create-policy \
  --policy-name DevOpsAgentSetupPolicy \
  --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Lambda",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:AddPermission",
        "lambda:DeleteFunction",
        "lambda:GetFunction",
        "lambda:PublishLayerVersion",
        "lambda:ListLayerVersions",
        "lambda:DeleteLayerVersion"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAM",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:DeleteRole",
        "iam:PassRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Cognito",
      "Effect": "Allow",
      "Action": [
        "cognito-idp:CreateUserPool",
        "cognito-idp:CreateUserPoolClient",
        "cognito-idp:CreateResourceServer",
        "cognito-idp:DeleteUserPool",
        "cognito-idp:DescribeUserPool"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AgentCoreGateway",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateMcpGateway",
        "bedrock-agentcore:CreateMcpGatewayTarget",
        "bedrock-agentcore:DeleteMcpGateway",
        "bedrock-agentcore:DeleteMcpGatewayTarget",
        "bedrock-agentcore:GetMcpGateway",
        "bedrock-agentcore:ListMcpGateways",
        "bedrock-agentcore:ListMcpGatewayTargets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DevOpsAgent",
      "Effect": "Allow",
      "Action": [
        "devops-agent:CreateAgentSpace",
        "devops-agent:DeleteAgentSpace",
        "devops-agent:GetAgentSpace",
        "devops-agent:AssociateAccount",
        "devops-agent:EnableOperatorApp",
        "devops-agent:RegisterService",
        "devops-agent:DeregisterService",
        "devops-agent:AssociateService",
        "devops-agent:DisassociateService",
        "devops-agent:ListAssociations"
      ],
      "Resource": "*"
    },
    {
      "Sid": "STS",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}'
```

Attach it to your operator role:

```bash
aws iam attach-role-policy \
  --role-name <YOUR_OPERATOR_ROLE> \
  --policy-arn arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):policy/DevOpsAgentSetupPolicy
```

### Environment

```bash
export AWS_REGION=us-west-2
export AWS_ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)
export DB_INSTANCE_ID=your-rds-instance-id
export DB_SECRET_ID=arn:aws:secretsmanager:us-west-2:123456789012:secret:your-secret-name
export SNS_TOPIC_NAME=your-sns-topic-name
export SECURITY_GROUP_ID=sg-xxxxxxxxx
export SUBNET1=subnet-xxxxxxxxx
export AGENTCORE_ROLE_ARN=arn:aws:iam::123456789012:role/AgentCoreDBOpsRole

pip install bedrock-agentcore-starter-toolkit mcp strands-agents strands-agents-tools -q
```

---

## Step 1 — Publish pymssql Lambda Layer

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

echo "Layer ARN: $LAYER_ARN"
rm -rf /tmp/pymssql-layer
```

---

## Step 2 — Package Lambda Functions

```bash
TOOLS_DIR=../../db-engines/sql-server/tools
CONFIG_DIR=../../db-engines/sql-server/config

rm -rf /tmp/health-pkg /tmp/query-pkg
mkdir -p /tmp/health-pkg /tmp/query-pkg

cp gateway_tools/health_handler.py /tmp/health-pkg/lambda_function.py
cp $TOOLS_DIR/database_health_tools.py /tmp/health-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/health-pkg/
cp -r $CONFIG_DIR /tmp/health-pkg/config
cd /tmp/health-pkg && zip -r /tmp/health-tools.zip . -q && cd -

cp gateway_tools/query_handler.py /tmp/query-pkg/lambda_function.py
cp $TOOLS_DIR/query_performance_tools.py /tmp/query-pkg/
cp $TOOLS_DIR/shared_utils.py /tmp/query-pkg/
cp -r $CONFIG_DIR /tmp/query-pkg/config
cd /tmp/query-pkg && zip -r /tmp/query-tools.zip . -q && cd -
```

---

## Step 3 — Create Health Tools Lambda

```bash
export SUBNET2="${SUBNET2:-$SUBNET1}"

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
```

---

## Step 4 — Create Query Tools Lambda

```bash
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
```

Clean up temp files:

```bash
rm -rf /tmp/health-pkg /tmp/query-pkg /tmp/health-tools.zip /tmp/query-tools.zip
```

---

## Step 5 — Grant Gateway Invoke Permissions

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

## Step 6 — Create MCP Gateway

This creates a Cognito OAuth authorizer, the MCP Gateway, and registers both Lambda targets with tool schemas. Uses the AgentCore SDK (no CLI equivalent exists for Gateway operations).

```bash
python3 setup_gateway.py
```

Outputs `gateway_config.json` with the Gateway URL and OAuth credentials.

---

## Step 7 — Verify Gateway

```bash
python3 agent_gateway.py
```

Ask `What is the current CPU utilization?` to confirm tools work end-to-end. Type `exit` to quit.

---

## Step 8 — Create Agent Space IAM Roles

```bash
aws iam create-role \
  --role-name DevOpsAgentRole-AgentSpace \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

aws iam create-role \
  --role-name DevOpsAgentRole-WebappAdmin \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
```

---

## Step 9 — Create Agent Space

```bash
export AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
  --space-name sql-server-dbops \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-AgentSpace \
  --region $AWS_REGION \
  --query 'agentSpaceId' --output text)

echo "Agent Space ID: $AGENT_SPACE_ID"
```

---

## Step 10 — Associate AWS Account

```bash
aws devops-agent associate-account \
  --agent-space-id $AGENT_SPACE_ID \
  --account-id $AWS_ACCOUNTID \
  --region $AWS_REGION
```

---

## Step 11 — Enable Web App

```bash
aws devops-agent enable-operator-app \
  --agent-space-id $AGENT_SPACE_ID \
  --role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-WebappAdmin \
  --region $AWS_REGION
```

---

## Step 12 — Register Gateway as MCP Server

```bash
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")
CLIENT_ID=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_id'])")
CLIENT_SECRET=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['client_secret'])")
TOKEN_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['client_info']['token_endpoint'])")

export MCP_SERVICE_ID=$(aws devops-agent register-service \
  --service mcpserver \
  --name "dbops-mcp" \
  --service-details "{\"mcpserver\": {\"name\": \"dbops-mcp\", \"endpoint\": \"$GATEWAY_URL\", \"description\": \"SQL Server diagnostic tools via AgentCore Gateway\", \"authorizationConfig\": {\"oAuthClientCredentials\": {\"clientName\": \"AgentCore-Gateway-OAuth\", \"clientId\": \"$CLIENT_ID\", \"clientSecret\": \"$CLIENT_SECRET\", \"exchangeUrl\": \"$TOKEN_URL\"}}}}" \
  --region $AWS_REGION \
  --query 'serviceId' --output text)

echo "MCP Service ID: $MCP_SERVICE_ID"
```

---

## Step 13 — Allowlist Tools

```bash
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --configuration '{"mcpserver": {"tools": ["dbops-health-tools___get_applications", "dbops-health-tools___get_cpu_utilization", "dbops-health-tools___get_database_connections", "dbops-health-tools___get_database_load", "dbops-health-tools___get_extended_database_load", "dbops-health-tools___get_free_storage", "dbops-health-tools___get_freeable_memory", "dbops-health-tools___get_iops", "dbops-health-tools___get_network_throughput", "dbops-health-tools___get_read_write_latency", "dbops-health-tools___get_top_sql", "dbops-health-tools___get_users", "dbops-health-tools___get_wait_events", "dbops-health-tools___send_email_notification", "dbops-query-tools___check_query_store_enabled", "dbops-query-tools___get_blocking_sessions", "dbops-query-tools___get_expensive_queries_from_cache", "dbops-query-tools___get_index_usage", "dbops-query-tools___get_query_execution_history", "dbops-query-tools___get_query_plan_from_cache", "dbops-query-tools___get_query_store_plan_summary", "dbops-query-tools___get_query_store_regressed_queries", "dbops-query-tools___get_query_store_top_queries", "dbops-query-tools___get_query_store_wait_stats", "dbops-query-tools___get_slow_queries", "dbops-query-tools___send_email_notification", "dbops-query-tools___suggest_indexes"]}}' \
  --region $AWS_REGION
```

---

## Step 14 — Upload Investigation Skill

```bash
cd skills && zip -r ../sql-server-investigation.zip sql-server-investigation/ -q && cd ..
```

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
3. Select `sql-server-investigation.zip`, Agent Type = **Generic**, click **Upload**

---

## Step 15 — Start an Investigation

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
aws devops-agent disassociate-service --agent-space-id $AGENT_SPACE_ID --service-id $MCP_SERVICE_ID --region $AWS_REGION
aws devops-agent deregister-service --service-id $MCP_SERVICE_ID --region $AWS_REGION
aws devops-agent delete-agent-space --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION

aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace
aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

python3 setup_gateway.py --cleanup

aws lambda delete-function --function-name dbops-health-tools --region $AWS_REGION
aws lambda delete-function --function-name dbops-query-tools --region $AWS_REGION

LAYER_VERSION=$(aws lambda list-layer-versions --layer-name pymssql-layer --region $AWS_REGION --query 'LayerVersions[0].Version' --output text)
aws lambda delete-layer-version --layer-name pymssql-layer --version-number $LAYER_VERSION --region $AWS_REGION

aws iam detach-role-policy --role-name <YOUR_OPERATOR_ROLE> --policy-arn arn:aws:iam::${AWS_ACCOUNTID}:policy/DevOpsAgentSetupPolicy
aws iam delete-policy --policy-arn arn:aws:iam::${AWS_ACCOUNTID}:policy/DevOpsAgentSetupPolicy

rm -f gateway_config.json sql-server-investigation.zip
```
