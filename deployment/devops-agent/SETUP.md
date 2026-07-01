# Setup Guide

Connect your SQL Server diagnostic tools to AWS DevOps Agent for managed, zero-code investigations.

---

## Prerequisites

### Tooling

- **AWS CLI v2.35 or later.** Earlier versions do not support the `mcpserversigv4`
  MCP service type used in Step 12 (you'll get
  `Unknown parameter in serviceDetails: "mcpserversigv4"`). Check with
  `aws --version` and upgrade if needed.

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
        "iam:PassRole",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AgentCoreGateway",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:CreateGateway",
        "bedrock-agentcore:CreateGatewayTarget",
        "bedrock-agentcore:DeleteGateway",
        "bedrock-agentcore:DeleteGatewayTarget",
        "bedrock-agentcore:GetGateway",
        "bedrock-agentcore:ListGateways",
        "bedrock-agentcore:ListGatewayTargets",
        "bedrock-agentcore:InvokeGateway"
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

Attach it to your operator role.

**Not sure what your operator role is?** It's the IAM identity you're running these
commands as. Check it:

```bash
aws sts get-caller-identity --query Arn --output text
```

- `arn:aws:iam::<acct>:user/<name>` → you're an **IAM user**. Use `attach-user-policy`
  with `--user-name <name>` instead of the role command below.
- `arn:aws:sts::<acct>:assumed-role/<ROLE_NAME>/<session>` → you're an **assumed role**.
  Your operator role is `<ROLE_NAME>` (the middle segment). Extract it with:

  ```bash
  export OPERATOR_ROLE=$(aws sts get-caller-identity --query Arn --output text | cut -d/ -f2)
  echo "Operator role: $OPERATOR_ROLE"
  ```

Then attach the policy:

```bash
aws iam attach-role-policy \
  --role-name "$OPERATOR_ROLE" \
  --policy-arn arn:aws:iam::${AWS_ACCOUNTID:-$(aws sts get-caller-identity --query Account --output text)}:policy/DevOpsAgentSetupPolicy
```

> If you already have broad permissions (e.g. an admin role), you can skip attaching
> this policy — it only exists to grant a least-privilege operator exactly what the
> runbook needs.

### Environment

```bash
export AWS_REGION=us-west-2
export AWS_ACCOUNTID=$(aws sts get-caller-identity --query Account --output text)
export DB_INSTANCE_ID=your-rds-instance-id
export DB_SECRET_ID=arn:aws:secretsmanager:us-west-2:123456789012:secret:your-secret-name
export SNS_TOPIC_NAME=your-sns-topic-name
export SECURITY_GROUP_ID=sg-xxxxxxxxx
export SUBNET1=subnet-xxxxxxxxx
export SUBNET2=subnet-yyyyyyyyy   # second subnet for Lambda VPC config; set to $SUBNET1 if you only have one
export AGENTCORE_ROLE_ARN=arn:aws:iam::123456789012:role/AgentCoreDBOpsRole

python3 -m pip install bedrock-agentcore-starter-toolkit mcp strands-agents strands-agents-tools -q
```

---

## Step 1 — Publish pymssql Lambda Layer

```bash
python3 -m pip install pymssql -t /tmp/pymssql-layer/python \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -q

cd /tmp/pymssql-layer && zip -r pymssql-layer-3.12.zip python -q && cd -

export LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name pymssql-layer \
  --compatible-runtimes python3.12 \
  --zip-file fileb:///tmp/pymssql-layer/pymssql-layer-3.12.zip \
  --region $AWS_REGION \
  --query 'LayerVersionArn' --output text)

echo "Layer ARN: $LAYER_ARN"
```

---

## Step 2 — Package Lambda Functions

> **Health tools are optional.** The investigation skill (Step 14) has the DevOps
> Agent read health signals — CPU utilization, memory, connections, load, and so on
> — through its own native CloudWatch and Performance Insights APIs rather than the
> health MCP tools. Package and deploy `dbops-health-tools` for a fully functional
> gateway, or omit every `dbops-health-tools` step (the marked lines in Steps 2, 3,
> 5, 6, and 13) if you only need the SQL-level `dbops-query-tools`.

From the repo root:

```bash
cd deployment/devops-agent/lambda/health && zip -r /tmp/health-tools.zip . -q && cd -   # optional (health tools)
cd deployment/devops-agent/lambda/query && zip -r /tmp/query-tools.zip . -q && cd -
```

---

## Step 3 — Create Health Tools Lambda

> **Optional** — skip this step if you are omitting the health tools (see Step 2).

```bash
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

---

## Step 5 — Grant Gateway Invoke Permissions

Skip the first command if you are omitting the health tools (see Step 2).

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

This creates an IAM-authenticated MCP Gateway and registers both Lambda targets with tool schemas. Uses the AgentCore SDK (no CLI equivalent exists for Gateway operations).

> **Omitting the health tools?** Run `setup_gateway.py --query-only` instead — it
> registers only the `dbops-query-tools` target and skips `dbops-health-tools`.

```bash
python3 deployment/devops-agent/setup_gateway.py
```

Outputs `gateway_config.json` with the Gateway URL.

---

## Step 7 — Verify Gateway

```bash
python3 deployment/devops-agent/agent_gateway.py
```

Ask `What is the current CPU utilization?` to confirm tools work end-to-end. Type `exit` to quit.

> **Note:** Uses IAM auth by default (signs requests with your AWS credentials). For Cognito OAuth, run with `--cognito` flag.

---

## Step 8 — Create Agent Space IAM Roles

```bash
aws iam create-role \
  --role-name DevOpsAgentRole-AgentSpace \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":"sts:AssumeRole","Condition":{"StringEquals":{"aws:SourceAccount":"'$AWS_ACCOUNTID'"},"ArnLike":{"aws:SourceArn":"arn:aws:aidevops:'$AWS_REGION':'$AWS_ACCOUNTID':agentspace/*"}}}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy

aws iam put-role-policy \
  --role-name DevOpsAgentRole-AgentSpace \
  --policy-name AllowCreateServiceLinkedRoles \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"AllowCreateServiceLinkedRoles\",\"Effect\":\"Allow\",\"Action\":[\"iam:CreateServiceLinkedRole\"],\"Resource\":[\"arn:aws:iam::${AWS_ACCOUNTID}:role/aws-service-role/resource-explorer-2.amazonaws.com/AWSServiceRoleForResourceExplorer\"]}]}"

aws iam create-role \
  --role-name DevOpsAgentRole-WebappAdmin \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"aidevops.amazonaws.com"},"Action":["sts:AssumeRole","sts:TagSession"],"Condition":{"StringEquals":{"aws:SourceAccount":"'$AWS_ACCOUNTID'"},"ArnLike":{"aws:SourceArn":"arn:aws:aidevops:'$AWS_REGION':'$AWS_ACCOUNTID':agentspace/*"}}}]}'

aws iam attach-role-policy \
  --role-name DevOpsAgentRole-WebappAdmin \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
```

---

## Step 9 — Create Agent Space

```bash
export AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
  --name sql-server-dbops \
  --description "Agent Space for SQL Server database operations" \
  --region $AWS_REGION \
  --query 'agentSpace.agentSpaceId' --output text)

echo "Agent Space ID: $AGENT_SPACE_ID"
```

---

## Step 10 — Associate AWS Account

```bash
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id aws \
  --configuration "{\"aws\": {\"assumableRoleArn\": \"arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-AgentSpace\", \"accountId\": \"$AWS_ACCOUNTID\", \"accountType\": \"monitor\"}}" \
  --region $AWS_REGION
```

---

## Step 11 — Enable Web App

```bash
aws devops-agent enable-operator-app \
  --agent-space-id $AGENT_SPACE_ID \
  --auth-flow iam \
  --operator-app-role-arn arn:aws:iam::${AWS_ACCOUNTID}:role/DevOpsAgentRole-WebappAdmin \
  --region $AWS_REGION
```

---

## Step 12 — Register Gateway as MCP Server

The gateway uses AWS IAM (SigV4) inbound auth. Registration only succeeds after
the signing role (`$AGENTCORE_ROLE_ARN`) can both be assumed by the DevOps Agent
service *and* invoke the gateway. Do 12a and 12b first, then register in 12c.

### 12a — Let the DevOps Agent service assume the signing role

Adds `aidevops.amazonaws.com` to the role's trust policy while preserving the
existing `bedrock-agentcore` and `lambda` trust:

```bash
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"

aws iam update-assume-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":[\"bedrock-agentcore.amazonaws.com\",\"lambda.amazonaws.com\"]},\"Action\":\"sts:AssumeRole\"},{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"aidevops.amazonaws.com\"},\"Action\":[\"sts:AssumeRole\",\"sts:TagSession\"],\"Condition\":{\"StringEquals\":{\"aws:SourceAccount\":\"${AWS_ACCOUNTID}\"}}}]}"
```

### 12b — Allow the signing role to invoke the gateway

```bash
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"

GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways --region $AWS_REGION \
  --query "items[?name=='dbops-mcp-gateway'].gatewayId | [0]" --output text)

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name InvokeDbopsGateway \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"AllowGatewayInvocation\",\"Effect\":\"Allow\",\"Action\":[\"bedrock-agentcore:InvokeGateway\"],\"Resource\":[\"arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNTID}:gateway/${GATEWAY_ID}\"]}]}"
```

### 12c — Register the gateway

IAM changes take a few seconds to propagate, so wait ~10s after 12a/12b before
running this:

```bash
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")

export MCP_SERVICE_ID=$(aws devops-agent register-service \
  --service mcpserversigv4 \
  --name "dbops-mcp" \
  --service-details "{\"mcpserversigv4\": {\"name\": \"dbops-mcp\", \"endpoint\": \"$GATEWAY_URL\", \"description\": \"SQL Server diagnostic tools via AgentCore Gateway\", \"authorizationConfig\": {\"region\": \"$AWS_REGION\", \"service\": \"bedrock-agentcore\", \"roleArn\": \"$AGENTCORE_ROLE_ARN\"}}}" \
  --region $AWS_REGION \
  --query 'serviceId' --output text)

echo "MCP Service ID: $MCP_SERVICE_ID"
```

A non-empty `MCP Service ID` means it worked.

> **Troubleshooting**
> - `ValidationException: Invalid STS role configuration ... Verify the role's trust policy`
>   → 12a didn't apply. Re-run it and confirm with
>   `aws iam get-role --role-name "$ROLE_NAME" --query 'Role.AssumeRolePolicyDocument'`.
> - `403 Authorization error - Insufficient permissions` → 12b hasn't propagated
>   yet. Wait ~20s and re-run 12c; the grant is correct, IAM is just catching up.

---

## Step 13 — Allowlist Tools

> The `--configuration` key must match the registered service type. Since the
> service was registered as `mcpserversigv4` (Step 12), the configuration uses the
> `mcpserversigv4` key (not `mcpserver`).

The command below allowlists all 27 tools (14 health + 13 query). If you omitted
the health tools (see Step 2), use the query-only variant that follows instead.

```bash
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --configuration '{"mcpserversigv4": {"tools": ["dbops-health-tools___get_applications", "dbops-health-tools___get_cpu_utilization", "dbops-health-tools___get_database_connections", "dbops-health-tools___get_database_load", "dbops-health-tools___get_extended_database_load", "dbops-health-tools___get_free_storage", "dbops-health-tools___get_freeable_memory", "dbops-health-tools___get_iops", "dbops-health-tools___get_network_throughput", "dbops-health-tools___get_read_write_latency", "dbops-health-tools___get_top_sql", "dbops-health-tools___get_users", "dbops-health-tools___get_wait_events", "dbops-health-tools___send_email_notification", "dbops-query-tools___check_query_store_enabled", "dbops-query-tools___get_blocking_sessions", "dbops-query-tools___get_expensive_queries_from_cache", "dbops-query-tools___get_index_usage", "dbops-query-tools___get_query_execution_history", "dbops-query-tools___get_query_plan_from_cache", "dbops-query-tools___get_query_store_plan_summary", "dbops-query-tools___get_query_store_regressed_queries", "dbops-query-tools___get_query_store_top_queries", "dbops-query-tools___get_query_store_wait_stats", "dbops-query-tools___get_slow_queries", "dbops-query-tools___send_email_notification", "dbops-query-tools___suggest_indexes"]}}' \
  --region $AWS_REGION
```

Query-only variant (health tools omitted):

```bash
aws devops-agent associate-service \
  --agent-space-id $AGENT_SPACE_ID \
  --service-id $MCP_SERVICE_ID \
  --configuration '{"mcpserversigv4": {"tools": ["dbops-query-tools___check_query_store_enabled", "dbops-query-tools___get_blocking_sessions", "dbops-query-tools___get_expensive_queries_from_cache", "dbops-query-tools___get_index_usage", "dbops-query-tools___get_query_execution_history", "dbops-query-tools___get_query_plan_from_cache", "dbops-query-tools___get_query_store_plan_summary", "dbops-query-tools___get_query_store_regressed_queries", "dbops-query-tools___get_query_store_top_queries", "dbops-query-tools___get_query_store_wait_stats", "dbops-query-tools___get_slow_queries", "dbops-query-tools___send_email_notification", "dbops-query-tools___suggest_indexes"]}}' \
  --region $AWS_REGION
```

---

## Step 14 — Upload Investigation Skill

```bash
cd deployment/devops-agent/skills && zip -r ../sql-server-investigation.zip sql-server-investigation/ -q && cd -
```

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
3. Select `deployment/devops-agent/sql-server-investigation.zip`, Agent Type = **Generic**, click **Upload**

---

## Step 15 — Add Agent Instructions (recommended)

Skills are *auto-selected* by matching your prompt against each skill's description.
When multiple skills are uploaded (for example the AWS-published `rds-operation-review`
skill alongside `sql-server-investigation`), a generic prompt like "high CPU" can be
ambiguous and the agent may not pick the SQL-Server skill. [Agent Instructions](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-agent-instructions.html)
are always-applied directives that remove that ambiguity — they tell the agent which
skill to use for which scenario, so you don't have to name the skill in every prompt.

Add the `AGENTS.md` from this directory in the console:

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Agent instructions**
3. Paste the contents of [`AGENTS.md`](AGENTS.md) (Agent Type **Investigation / INCIDENT_RCA**) and save

With this in place, any SQL Server / RDS SQL Server investigation automatically uses
the `sql-server-investigation` skill — no need to name it in the prompt.

---

## Step 16 — Connect CloudWatch Alarms (event-driven investigations)

This step wires CloudWatch Alarms to DevOps Agent so that an alarm firing
automatically starts an investigation — no human in the loop.

The flow: **CloudWatch Alarm → Lambda (direct invoke) → DevOps Agent Webhook**

### 16a — Generate the Webhook URL and Secret

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Capabilities** tab
3. Under **Webhooks**, find **Agent Space Webhook** and click **Add** 
4. The system generates an HMAC key pair — copy the **Webhook URL** and the **Secret Key** immediately

### 16b — Store Webhook Credentials in Secrets Manager

```bash
export WEBHOOK_URL="<paste webhook URL>"
export WEBHOOK_SECRET="<paste webhook secret>"

export WEBHOOK_SECRET_ARN=$(aws secretsmanager create-secret \
  --name dbops-devops-agent-webhook \
  --description "DevOps Agent webhook credentials for alarm-triggered investigations" \
  --secret-string "{\"webhookUrl\":\"$WEBHOOK_URL\",\"webhookSecret\":\"$WEBHOOK_SECRET\"}" \
  --region $AWS_REGION \
  --query 'ARN' --output text)

echo "Webhook Secret ARN: $WEBHOOK_SECRET_ARN"
```

### 16c — Package and Deploy the Webhook Executor Lambda

```bash
cd deployment/devops-agent/lambda/webhook && zip -r /tmp/webhook-executor.zip . -q && cd -

aws lambda create-function \
  --function-name dbops-webhook-executor \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role $AGENTCORE_ROLE_ARN \
  --zip-file fileb:///tmp/webhook-executor.zip \
  --timeout 30 \
  --memory-size 128 \
  --environment "Variables={WEBHOOK_SECRET_ARN=$WEBHOOK_SECRET_ARN}" \
  --region $AWS_REGION \
  --query 'FunctionArn' --output text
```

> This Lambda does NOT need VPC access — it calls the public DevOps Agent
> webhook endpoint and Secrets Manager over the internet.

### 16d — Grant the Lambda Role Access to the Webhook Secret

```bash
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name WebhookSecretRead \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"$WEBHOOK_SECRET_ARN\"}]}"
```

### 16e — Allow CloudWatch Alarms to Invoke the Lambda

```bash
aws lambda add-permission \
  --function-name dbops-webhook-executor \
  --statement-id cloudwatch-alarm-invoke \
  --action lambda:InvokeFunction \
  --principal lambda.alarms.cloudwatch.amazonaws.com \
  --source-account $AWS_ACCOUNTID \
  --region $AWS_REGION
```

### 16f — Create Alarms with the Lambda as an Action

Create three CloudWatch alarms on the RDS instance that invoke the webhook
executor Lambda when they breach. Each alarm monitors a different symptom:
**HighCPU** (average CPU > 80%), **HighConnections** (active connections > 10),
and **HighReadLatency** (read latency > 20 ms). Thresholds are intentionally
low for demo purposes — adjust them for production workloads.

```bash
export WEBHOOK_LAMBDA_ARN=$(aws lambda get-function \
  --function-name dbops-webhook-executor --region $AWS_REGION \
  --query 'Configuration.FunctionArn' --output text)

aws cloudwatch put-metric-alarm \
  --alarm-name "dbops-demo-HighCPU" \
  --alarm-description "RDS CPU utilization high — triggers DevOps Agent investigation" \
  --namespace AWS/RDS --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
  --statistic Average --period 60 --evaluation-periods 1 \
  --threshold 80 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions $WEBHOOK_LAMBDA_ARN \
  --region $AWS_REGION

aws cloudwatch put-metric-alarm \
  --alarm-name "dbops-demo-HighConnections" \
  --alarm-description "RDS database connections high — triggers DevOps Agent investigation" \
  --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
  --statistic Average --period 60 --evaluation-periods 1 \
  --threshold 10 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions $WEBHOOK_LAMBDA_ARN \
  --region $AWS_REGION

aws cloudwatch put-metric-alarm \
  --alarm-name "dbops-demo-HighReadLatency" \
  --alarm-description "RDS read latency high — triggers DevOps Agent investigation" \
  --namespace AWS/RDS --metric-name ReadLatency \
  --dimensions Name=DBInstanceIdentifier,Value=$DB_INSTANCE_ID \
  --statistic Average --period 60 --evaluation-periods 1 \
  --threshold 0.02 --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions $WEBHOOK_LAMBDA_ARN \
  --region $AWS_REGION
```

> **Thresholds are intentionally low** so they trip quickly during the demo.
> Adjust for production workloads.

### 16g — Test the Integration

Invoke the alarm manually to verify end-to-end:

```bash
aws cloudwatch set-alarm-state \
  --alarm-name "dbops-demo-HighCPU" \
  --state-value ALARM \
  --state-reason "Manual test of alarm-to-investigation flow" \
  --region $AWS_REGION
```

Within seconds, check the DevOps Agent Web App — a new investigation should
appear, triggered by the alarm. The agent will use the `sql-server-investigation`
skill, read CloudWatch/Database Insights via its IAM role, and call your MCP
tools through the Gateway when deeper SQL-level data is needed.

---

## Step 17 — Start an Investigation (manual)

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
# Webhook executor
aws lambda delete-function --function-name dbops-webhook-executor --region $AWS_REGION
aws secretsmanager delete-secret --secret-id dbops-devops-agent-webhook --force-delete-without-recovery --region $AWS_REGION
aws cloudwatch delete-alarms --alarm-names "dbops-demo-HighCPU" "dbops-demo-HighConnections" "dbops-demo-HighReadLatency" --region $AWS_REGION
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name WebhookSecretRead
```

```bash
# Find the association ID for the MCP service, then disassociate it
ASSOCIATION_ID=$(aws devops-agent list-associations --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION \
  --query "associations[?serviceId=='$MCP_SERVICE_ID'].associationId | [0]" --output text)
aws devops-agent disassociate-service --agent-space-id $AGENT_SPACE_ID --association-id $ASSOCIATION_ID --region $AWS_REGION
aws devops-agent deregister-service --service-id $MCP_SERVICE_ID --region $AWS_REGION
aws devops-agent delete-agent-space --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION

aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace
aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

python3 deployment/devops-agent/setup_gateway.py --cleanup

aws lambda delete-function --function-name dbops-health-tools --region $AWS_REGION
aws lambda delete-function --function-name dbops-query-tools --region $AWS_REGION

LAYER_VERSION=$(aws lambda list-layer-versions --layer-name pymssql-layer --region $AWS_REGION --query 'LayerVersions[0].Version' --output text)
aws lambda delete-layer-version --layer-name pymssql-layer --version-number $LAYER_VERSION --region $AWS_REGION

aws iam detach-role-policy --role-name "$OPERATOR_ROLE" --policy-arn arn:aws:iam::${AWS_ACCOUNTID}:policy/DevOpsAgentSetupPolicy
aws iam delete-policy --policy-arn arn:aws:iam::${AWS_ACCOUNTID}:policy/DevOpsAgentSetupPolicy
```
