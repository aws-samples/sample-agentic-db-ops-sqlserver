# AWS DevOps Agent Integration

Connects [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html)
to the SQL Server diagnostic tools in this repo. DevOps Agent reads CloudWatch and
Database Insights on its own. For SQL-level data (blocking, Query Store, plan cache,
indexes) it calls 13 tools hosted in a Lambda function behind an AgentCore Gateway.
CloudWatch alarms on the RDS instance start investigations automatically.

The integration is one CloudFormation stack ([`dbops-devops-agent.yaml`](dbops-devops-agent.yaml))
plus two steps outside it: uploading the investigation skill (CLI, Step 2) and
creating the webhook credentials (console, Step 3).

## How it works

```
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────┐
│ DevOps Agent      │─────▶│ AgentCore Gateway │─────▶│ dbops-query-tools │
│ (web app)         │      │ (MCP, SigV4 auth) │      │ Lambda            │
└───────────────────┘      └───────────────────┘      └─────────┬─────────┘
          ▲                                                     │ T-SQL
          │ webhook POST (HMAC-SHA256)                          ▼
┌─────────┴─────────┐      ┌───────────────────┐      ┌───────────────────┐
│ dbops-webhook-    │◀─────│ CloudWatch alarm  │      │ RDS SQL Server    │
│ executor Lambda   │      │ (RDS metric)      │      │ (DMVs)            │
└───────────────────┘      └───────────────────┘      └───────────────────┘
```

1. The `dbops-query-tools` Lambda runs T-SQL diagnostics against the RDS instance.
2. AgentCore Gateway exposes those tools as an MCP server with IAM (SigV4) authentication.
3. DevOps Agent is registered with the gateway and allowed to call all 13 tools.
4. The `sql-server-investigation` skill tells the agent which tools to use and in what order.
5. When an alarm fires, the webhook executor Lambda sends a signed request to the Agent
   Space webhook, which starts an investigation.

## What the stack creates

The stack creates 19 resources. The investigation skill is uploaded in Step 2, not by
the stack.

### Compute

- **pymssql Lambda layer**: the `pymssql` driver the query Lambda uses to connect to
  SQL Server.
- **`dbops-query-tools`** (Lambda in your VPC): 13 tools covering blocking chains,
  Query Store, slow queries, plan cache, and index usage and suggestions.
- **`dbops-webhook-executor`** (Lambda, no VPC): receives a CloudWatch alarm and sends
  an HMAC-signed request to the DevOps Agent webhook.
- **Invoke permissions**: let the gateway call the query Lambda and the alarms call the
  webhook executor.

### IAM

- **`<stack name>-signing`**: execution role for the query Lambda, the gateway's role,
  and the SigV4 signing role for the MCP service. Read access to CloudWatch,
  Performance Insights, RDS, the DB secret, and SNS.
- **`<stack name>-AgentSpace`**: assumed by DevOps Agent to read your account.
- **`<stack name>-WebappAdmin`**: used by the operator web app.

### AgentCore Gateway

- **`dbops-mcp-gateway`**: MCP gateway with IAM (SigV4) inbound authentication.
- **Gateway target**: registers the query Lambda with the schemas for all 13 tools.

### DevOps Agent

- **Agent Space `sql-server-dbops`** (set with the `AgentSpaceName` parameter), with
  the operator web app enabled.
- **AWS account association**: lets the agent read your account through the Agent
  Space role.
- **MCP service registration**: registers the gateway and allows the agent to call the
  13 tools.

### Alarms

- **Webhook secret `dbops-devops-agent-webhook`**: created with placeholder values that
  you replace in Step 3.
- **Three demo alarms** on the RDS instance (`dbops-demo-HighCPU`,
  `dbops-demo-HighConnections`, `dbops-demo-HighReadLatency`), each wired to the
  webhook executor.

### Resource names

IAM role names include the stack name, so you can deploy the stack in more than one
region of the same account. The Lambda functions, layer, gateway, secret, and alarms
have fixed names, so deploy one copy per region. Keep the stack name to 50 characters
or fewer so role names stay within the 64-character IAM limit.

## Prerequisites

Run every command in this guide from `deployment/devops-agent/`, with `AWS_REGION` set:

```bash
cd deployment/devops-agent    # from the repo root
export AWS_REGION=us-west-2   # region for the base stack and this stack
```

### Tools

- AWS CLI v2
- `jq` (Step 1 shows a Python alternative)
- `zip` and Python 3 for the skill upload in Step 2

### Base infrastructure

This stack uses an existing RDS SQL Server environment. Deploy
[`templates/infrastructure.yaml`](../../templates/infrastructure.yaml) first. It creates
the VPC, the RDS SQL Server instance, the DB secret, and the SNS topic.

```bash
aws cloudformation deploy \
  --template-file ../../templates/infrastructure.yaml \
  --stack-name dbops \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AlertEmail=you@example.com
```

That template names its IAM roles and S3 buckets after the stack, without the region.
If you deploy it in a second region of the same account, use a different stack name
(for example `dbops-us-east-1`) and use that name wherever this guide says `dbops`.

### Artifact bucket

In Step 1, `aws cloudformation package` uploads the pymssql layer and the two Lambda
code bundles to an S3 bucket and writes `packaged.yaml`, which points at them. The
bucket must be in the same region as the stack. This creates one if it doesn't already
exist (in us-east-1, S3 buckets are created without a location constraint):

```bash
export YOUR_ARTIFACT_BUCKET="dbops-devops-agent-artifacts-$(aws sts get-caller-identity --query Account --output text)-$AWS_REGION"

if [ "$AWS_REGION" = "us-east-1" ]; then LOCATION_ARGS=(); else
  LOCATION_ARGS=(--create-bucket-configuration LocationConstraint="$AWS_REGION"); fi

aws s3api head-bucket --bucket "$YOUR_ARTIFACT_BUCKET" 2>/dev/null ||
  aws s3api create-bucket --bucket "$YOUR_ARTIFACT_BUCKET" --region "$AWS_REGION" \
    "${LOCATION_ARGS[@]}"
```

### Deploy role (optional)

If you deploy with administrator permissions, skip this section.

Otherwise, deploy [`cfn-service-role.yaml`](cfn-service-role.yaml) first. It creates a
role with only the permissions this stack needs. You pass its ARN to `deploy` in
Step 1.

```bash
aws cloudformation deploy \
  --template-file cfn-service-role.yaml \
  --stack-name dbops-devops-agent-cfn-role \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION"

export CFN_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name dbops-devops-agent-cfn-role --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" --output text)
```

### parameters.json

The stack takes six parameters from the base stack's outputs. Build `parameters.json`
from them:

```bash
aws cloudformation describe-stacks --stack-name dbops --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs' --output json \
| jq '(map({(.OutputKey): .OutputValue}) | add) as $o | [
    {ParameterKey: "DBInstanceId",    ParameterValue: $o.DBInstanceId},
    {ParameterKey: "DBSecretArn",     ParameterValue: $o.DBSecretId},
    {ParameterKey: "SnsTopicName",    ParameterValue: $o.SNSTopicName},
    {ParameterKey: "SecurityGroupId", ParameterValue: $o.SecurityGroupId},
    {ParameterKey: "Subnet1",         ParameterValue: $o.Subnet1},
    {ParameterKey: "Subnet2",         ParameterValue: $o.Subnet2}
  ]' > parameters.json

cat parameters.json
```

Check that no value is `null`. To fill it in by hand instead, copy
[`parameters.example.json`](parameters.example.json) to `parameters.json` and replace
the placeholders with the outputs listed above.

## Step 1: Deploy the stack

`package` uploads the code artifacts, and `deploy` creates the stack:

```bash
aws cloudformation package \
  --template-file dbops-devops-agent.yaml \
  --s3-bucket "$YOUR_ARTIFACT_BUCKET" \
  --output-template-file packaged.yaml \
  --region "$AWS_REGION"

aws cloudformation deploy \
  --template-file packaged.yaml \
  --stack-name dbops-devops-agent \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides $(jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' parameters.json)
```

If you created the deploy role, add `--role-arn "$CFN_ROLE_ARN"` to the `deploy`
command.

To choose the signing role's name yourself, add `SigningRoleName=<name>` to
`--parameter-overrides`. The name must not match an existing IAM role.

If `jq` isn't installed, generate the overrides with Python instead:

```bash
--parameter-overrides $(python3 -c "import json; print(' '.join(f\"{p['ParameterKey']}={p['ParameterValue']}\" for p in json.load(open('parameters.json'))))")
```

> **If `McpService` fails with `AccessDenied`:** the new IAM role can take a minute to
> become usable. On a first deployment the stack rolls back, so delete it, wait a
> minute, and deploy again:
>
> ```bash
> aws cloudformation delete-stack --stack-name dbops-devops-agent --region "$AWS_REGION"
> aws cloudformation wait stack-delete-complete --stack-name dbops-devops-agent --region "$AWS_REGION"
> ```

Read the stack outputs (gateway URL, Agent Space ID, webhook secret ARN):

```bash
aws cloudformation describe-stacks --stack-name dbops-devops-agent \
  --region "$AWS_REGION" --query 'Stacks[0].Outputs' --output table
```

## Step 2: Upload the investigation skill

The skill (`skills/sql-server-investigation/`) and the agent instructions (`AGENTS.md`)
aren't part of the stack. You upload them to the Agent Space with the DevOps Agent asset
API, so you can change them without redeploying. Set `AGENT_SPACE_ID` from the Step 1
outputs, then:

```bash
AGENT_SPACE_ID=<AgentSpaceId from Step 1 outputs>

# Skill (SKILL.md + references/) uploaded as a zip.
# The name and description come from the SKILL.md frontmatter.
( cd skills/sql-server-investigation && zip -rq /tmp/sql-server-investigation.zip SKILL.md references )
aws devops-agent create-asset \
  --agent-space-id "$AGENT_SPACE_ID" \
  --asset-type skill \
  --metadata '{"agent_types":["GENERIC"]}' \
  --content "{\"zip\":{\"zipFile\":\"$(base64 < /tmp/sql-server-investigation.zip | tr -d '\n')\"}}" \
  --region "$AWS_REGION"

# Agent instructions (single file AGENTS.md).
aws devops-agent create-asset \
  --agent-space-id "$AGENT_SPACE_ID" \
  --asset-type agents_md \
  --metadata '{"agent_type":"INCIDENT_RCA"}' \
  --content "{\"file\":{\"path\":\"AGENTS.md\",\"body\":{\"text\":$(python3 -c 'import json;print(json.dumps(open("AGENTS.md").read()))')}}}" \
  --region "$AWS_REGION"
```

To change the skill later, edit the Markdown and upload it again with
`aws devops-agent update-asset`.

## Step 3: Create the webhook credentials (console)

The console generates the webhook URL and HMAC secret. CloudFormation can't create them.

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces).
2. Choose **sql-server-dbops**, then **Capabilities**, **Webhooks**, **Agent Space Webhook**, **Add**.
3. Copy the **Webhook URL** and **Secret Key**.
4. Store them in the secret the stack created:

```bash
aws secretsmanager put-secret-value \
  --secret-id dbops-devops-agent-webhook \
  --secret-string "{\"webhookUrl\":\"<paste URL>\",\"webhookSecret\":\"<paste secret>\"}" \
  --region "$AWS_REGION"
```

The alarms and the webhook executor are already connected. Once the secret holds real
values, alarms start investigations.

## Step 4: Verify

Open the web app from the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
(choose **sql-server-dbops**), or get its URL:

```bash
aws devops-agent get-agent-space --agent-space-id "$AGENT_SPACE_ID" \
  --region "$AWS_REGION" --query 'agentSpace.operatorApp.operatorAppUrl' --output text
```

### Alarm-triggered investigation

Set an alarm to `ALARM` to test the full flow:

```bash
aws cloudwatch set-alarm-state \
  --alarm-name "dbops-demo-HighCPU" \
  --state-value ALARM \
  --state-reason "Manual test of alarm-to-investigation flow" \
  --region "$AWS_REGION"
```

A new investigation should appear in the web app within a minute. The agent follows the
`sql-server-investigation` skill, reads CloudWatch and Database Insights through its IAM
role, and calls the MCP tools when it needs SQL-level data.

> The demo alarm thresholds are low so they trip quickly. Raise them for production
> workloads.

### Manual investigation

In the web app, try:

```text
Give me a complete database health report
The database is experiencing high CPU. Diagnose the root cause.
Are there any blocking sessions affecting performance?
```

## Tool reference

| Gateway target | Tools | Data source |
|---|---|---|
| `dbops-query-tools` (13) | Slow queries, blocking, Query Store, indexes, execution plans | SQL Server DMVs and Query Store |

In DevOps Agent, tool names take the form `<target>___<tool>` (three underscores), for
example `dbops-query-tools___get_blocking_sessions`.

## Cleanup

Delete the assets you uploaded in Step 2 first, because they aren't part of the stack.
Then delete the stack:

```bash
# 1. Remove the uploaded assets (skill and AGENTS.md)
for A in $(aws devops-agent list-assets --agent-space-id "$AGENT_SPACE_ID" \
             --region "$AWS_REGION" --query 'items[].assetId' --output text); do
  aws devops-agent delete-asset --agent-space-id "$AGENT_SPACE_ID" --asset-id "$A" --region "$AWS_REGION"
done

# 2. Delete the stack
aws cloudformation delete-stack --stack-name dbops-devops-agent --region "$AWS_REGION"
aws cloudformation wait stack-delete-complete --stack-name dbops-devops-agent --region "$AWS_REGION"
```

Deleting the stack removes the Agent Space, gateway, target, MCP service, associations,
Lambda functions, layer, IAM roles, secret, and alarms. If you created the deploy role,
delete the `dbops-devops-agent-cfn-role` stack too.
