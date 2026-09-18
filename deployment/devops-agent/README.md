# AWS DevOps Agent Integration

Connect your SQL Server diagnostic tools to [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html) for managed, zero-code investigations through a web interface. This is an alternative to invoking the agents directly on AgentCore Runtime (`agentcore invoke`) — the same health and query capabilities, surfaced in a managed web app instead of the CLI.

## How It Works

```
┌──────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  DevOps Agent    │────▶│ AgentCore Gateway │────▶│  Lambda Functions   │
│  (Web App)       │     │  (MCP endpoint)   │     │  (your tools)       │
└──────────────────┘     └──────────────────┘     └─────────────────────┘
        ▲                        │                         │
        │                 IAM auth + routing         CloudWatch, DMVs,
        │                  (SigV4)                  Database Insights
        │
        │  Webhook POST (HMAC-SHA256)
        │
┌──────────────────┐     ┌──────────────────┐
│  Webhook Lambda  │◀────│ CloudWatch Alarm  │◀─── RDS metric threshold
│  (bridge)        │     │  (direct invoke)  │
└──────────────────┘     └──────────────────┘
```

1. Your existing tools (health + query) are packaged as Lambda functions
2. AgentCore Gateway exposes them as MCP endpoints with AWS IAM (SigV4) authentication
3. DevOps Agent connects to the Gateway and discovers all 27 tools
4. An investigation skill teaches the agent your structured troubleshooting methodology
5. CloudWatch Alarms invoke a webhook executor Lambda that triggers investigations automatically

## Deploy with CloudFormation (recommended)

A single stack — [`dbops-devops-agent.yaml`](dbops-devops-agent.yaml) — provisions
the whole integration (Lambdas, layer, gateway + targets, agent space, web app, MCP
service, tool allowlist, skill/agent-instruction assets, webhook secret, executor
Lambda, and alarms). The only manual step is minting the webhook URL+secret in the
console. **[SETUP.md](SETUP.md) is the authoritative walkthrough** — the commands
below are a summary.

```bash
cd deployment/devops-agent
export AWS_REGION=us-west-2
export YOUR_ARTIFACT_BUCKET="dbops-devops-agent-artifacts-$(aws sts get-caller-identity --query Account --output text)-$AWS_REGION"
aws s3api create-bucket --bucket "$YOUR_ARTIFACT_BUCKET" --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" 2>/dev/null || true

cp parameters.example.json parameters.json    # fill in your dbops stack outputs

aws cloudformation package --template-file dbops-devops-agent.yaml \
  --s3-bucket "$YOUR_ARTIFACT_BUCKET" --output-template-file packaged.yaml --region "$AWS_REGION"

aws cloudformation deploy --template-file packaged.yaml --stack-name dbops-devops-agent \
  --region "$AWS_REGION" --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides $(jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' parameters.json)
```

> `--parameter-overrides` takes inline `Key=Value` pairs (not `file://`), so the `jq`
> expression turns `parameters.json` into pairs. Keep it **last** on the command — it
> is greedy and swallows any flag after it.

**Optional least-privilege deploy role:** deploy [`cfn-service-role.yaml`](cfn-service-role.yaml)
first and add `--role-arn "$CFN_ROLE_ARN"` (before `--parameter-overrides`). It carries
an enumerated, wildcard-free policy verified by an end-to-end deploy — suitable for
customer-facing / AppSec-reviewed accounts.

Then populate the webhook secret (SETUP.md Step 2) and verify. Teardown is a single
`aws cloudformation delete-stack --stack-name dbops-devops-agent`.

---

# Scripted path (alternative)

> **Skip this entire section if you deployed with CloudFormation above.** The steps
> below are the manual, script-driven alternative — they produce the *same* resources.
> Use one path or the other, not both.

## Prerequisites (scripted path)

- A reachable RDS SQL Server environment (e.g. from `templates/infrastructure.yaml`)
- `.env` sourced with all environment variables (region, account, `AGENTCORE_ROLE_ARN`,
  DB instance/secret, SNS topic, subnets, security group)
- Python 3.12+ and `bedrock-agentcore-starter-toolkit` installed

## Step 1: Deploy the Gateway

This packages your health and query tools as Lambda functions, creates the gateway
(AWS IAM / SigV4 auth), and registers both Lambda targets with AgentCore Gateway.

```bash
cd deployment/devops-agent
chmod +x deploy_gateway.sh
./deploy_gateway.sh
```

This creates `gateway_config.json` with the Gateway URL.

> **Note — health tools are optional.** The gateway deploys both the
> `dbops-health-tools` and `dbops-query-tools` Lambda targets. The health tools are
> optional: the investigation skill (Step 4) has the DevOps Agent read health
> signals — CPU utilization, memory, connections, load, and so on — through its
> own native CloudWatch and Performance Insights APIs rather than these MCP tools.
> To deploy the SQL-level query tools only, run `./deploy_gateway.sh --query-only`.

> **What it does:** publishes the pymssql layer, packages and creates each tool
> Lambda, creates the gateway, and registers the targets. Read
> [`deploy_gateway.sh`](deploy_gateway.sh) and [`setup_gateway.py`](setup_gateway.py)
> for the exact steps. (The CloudFormation path at the top does all of this
> declaratively.)

### Verify Gateway

```bash
python3 agent_gateway.py
```

Ask: "What is the current CPU utilization?" — confirms tools work end-to-end via MCP.

## Step 2: Create the Agent Space

Create the Agent Space IAM roles, the Agent Space itself, associate your AWS
account, and enable the Web App. [`setup_agent_space.sh`](setup_agent_space.sh)
automates all of this:

```bash
./setup_agent_space.sh
```

> Run it from `deployment/devops-agent/` with `.env` sourced (so `$AWS_REGION`,
> `$AWS_ACCOUNTID`, and `$AGENTCORE_ROLE_ARN` are set). It exports
> `$AGENT_SPACE_ID`, which the next step uses.

## Step 3: Connect Gateway as MCP Server

Register the AgentCore Gateway (deployed in Step 1) as an MCP server on the Agent
Space and allowlist all 27 tools. The gateway uses AWS IAM (SigV4) auth.
[`setup_agent_space.sh`](setup_agent_space.sh) (Step 2) also performs the MCP
service registration and tool allowlist.

> These read `gateway_config.json` (from Step 1) for the Gateway URL and use
> `$AGENT_SPACE_ID` and `$AGENTCORE_ROLE_ARN`.

## Step 4: Upload Investigation Skill

The skill teaches DevOps Agent a structured troubleshooting methodology: triage → diagnose → drill down → correlate → recommend.

1. Zip the skill:
   ```bash
   cd skills && zip -r ../sql-server-investigation.zip sql-server-investigation/ && cd ..
   ```
2. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
3. Click **sql-server-dbops** → **Operator access** → **Skills** → **Add skill** → **Upload skill**
4. Select `sql-server-investigation.zip`, set Agent Type to **Generic**, click **Upload**

### Add Agent Instructions (recommended)

When multiple skills are uploaded, a generic prompt like "high CPU" can be ambiguous.
[Agent Instructions](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent-agent-instructions.html)
tell the agent which skill to use for which scenario.

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops** → **Operator access** → **Agent instructions**
3. Paste the contents of [`AGENTS.md`](AGENTS.md) (Agent Type **Investigation / INCIDENT_RCA**) and save

## Step 5: Connect CloudWatch Alarms (event-driven investigations)

Wire CloudWatch Alarms to DevOps Agent so that threshold breaches automatically
start investigations — no human in the loop.

The flow: **CloudWatch Alarm → Lambda (direct invoke) → DevOps Agent Webhook**

1. Generate a webhook in the DevOps Agent console (click sql-server-dbops → Capabilities → Webhooks → Add)
2. Store the webhook URL and secret in Secrets Manager
3. Deploy the webhook executor Lambda (`lambda/webhook/lambda_function.py`)
4. Create CloudWatch alarms with the Lambda ARN as the alarm action

The webhook URL/secret (step 1 above) can only be minted in the console — there is no
create-webhook API. Everything else here you create with the AWS CLI.

---

# Using the agent (either path)

## Use It

Open the DevOps Agent Web App from the
[DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
(select **sql-server-dbops**), or fetch the direct URL with
`aws devops-agent get-agent-space --agent-space-id <id> --query 'agentSpace.operatorApp.operatorAppUrl'`.

**Manual** — start an investigation:

```
"Give me a complete database health report"
"The database is experiencing high CPU. Diagnose the root cause."
"Are there any blocking sessions affecting performance?"
```

**Alarm-triggered** — When a CloudWatch alarm fires (e.g. CPU > 80%), the webhook
executor Lambda automatically triggers a DevOps Agent investigation. The agent uses
the investigation skill, reads CloudWatch/Database Insights via its IAM role, and
calls your MCP tools through the Gateway for SQL-level detail.

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

**CloudFormation deploy:** one command tears down everything —

```bash
aws cloudformation delete-stack --stack-name dbops-devops-agent --region "$AWS_REGION"
```

**Scripted path:** if you deployed with the scripts instead of CloudFormation, tear
down in this order (`deploy_gateway.sh --cleanup` handles the gateway/Lambdas/layer):

```bash
# 1. Webhook executor and alarms (Step 5)
aws lambda delete-function --function-name dbops-webhook-executor --region $AWS_REGION
aws secretsmanager delete-secret --secret-id dbops-devops-agent-webhook --force-delete-without-recovery --region $AWS_REGION
aws cloudwatch delete-alarms --alarm-names "dbops-demo-HighCPU" "dbops-demo-HighConnections" "dbops-demo-HighReadLatency" --region $AWS_REGION
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name WebhookSecretRead 2>/dev/null || true

# 2. Disassociate the MCP service (disassociate takes the ASSOCIATION id, not the service id)
ASSOCIATION_ID=$(aws devops-agent list-associations --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION \
  --query "associations[?serviceId=='$MCP_SERVICE_ID'].associationId | [0]" --output text)
aws devops-agent disassociate-service --agent-space-id $AGENT_SPACE_ID --association-id $ASSOCIATION_ID --region $AWS_REGION

# 3. Deregister the MCP service, then delete the Agent Space
aws devops-agent deregister-service --service-id $MCP_SERVICE_ID --region $AWS_REGION
aws devops-agent delete-agent-space --agent-space-id $AGENT_SPACE_ID --region $AWS_REGION

# 4. Delete the Agent Space IAM roles
aws iam detach-role-policy --role-name DevOpsAgentRole-AgentSpace --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-AgentSpace
aws iam detach-role-policy --role-name DevOpsAgentRole-WebappAdmin --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy
aws iam delete-role --role-name DevOpsAgentRole-WebappAdmin

# 5. Delete the Gateway, Lambdas, and pymssql layer (run from this directory)
./deploy_gateway.sh --cleanup

# 6. (Optional) Remove the gateway-specific grants added to the SHARED execution role.
#    Do NOT delete AgentCoreDBOpsRole itself — the 5 AgentCore agents use it.
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name InvokeDbopsGateway 2>/dev/null || true
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name GatewayInvokeDbopsLambdas 2>/dev/null || true
```
