# AWS DevOps Agent Integration

Connect your SQL Server diagnostic tools to [AWS DevOps Agent](https://docs.aws.amazon.com/devopsagent/latest/userguide/about-aws-devops-agent.html)
for managed, zero-code investigations through a web interface. This is an alternative
to invoking the agents directly on AgentCore Runtime (`agentcore invoke`): the same
health and query capabilities, surfaced in a managed web app instead of the CLI.

The whole integration deploys as a **single CloudFormation stack**
([`dbops-devops-agent.yaml`](dbops-devops-agent.yaml)). Only one step, minting the
webhook credentials, must be done by hand in the console.

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

1. Your SQL-level query tools are packaged as a Lambda function
2. AgentCore Gateway exposes them as MCP endpoints with AWS IAM (SigV4) authentication
3. DevOps Agent connects to the Gateway and discovers all 13 tools
4. An investigation skill teaches the agent your structured troubleshooting methodology
5. CloudWatch Alarms invoke a webhook executor Lambda that triggers investigations automatically

## What the stack provisions

One `aws cloudformation deploy` creates the integration: 21 resources across six
areas. All resource names are fixed (`dbops-*`, `sql-server-dbops`,
`AgentCoreDBOpsRole`) so re-deploys and teardown are predictable.

### Compute (the diagnostic tools)

- **pymssql Lambda layer**: bundles the `pymssql` driver so the query Lambda can
  open a live T-SQL connection to the RDS instance.
- **`dbops-query-tools`** (VPC Lambda, 13 tools): SQL-level diagnostics over a
  direct DB connection, covering blocking chains, Query Store, slow queries, plan
  cache, and index usage/suggestions. (Host metrics such as CPU, memory, and
  latency are read by the DevOps Agent natively, so no health-tool Lambda is needed.)
- **`dbops-webhook-executor`** (non-VPC Lambda): the bridge that receives a
  CloudWatch alarm and POSTs an HMAC-signed request to the DevOps Agent webhook to
  start an investigation.
- **Invoke permissions**: resource policies allowing the AgentCore gateway to
  invoke the tool Lambdas and CloudWatch alarms to invoke the webhook executor.

### IAM

- **Signing/execution role (`AgentCoreDBOpsRole`)**: one role, three hats. It is the
  tool Lambdas' execution role, the gateway's role, and the SigV4 signing role for
  the MCP service. It holds least-privilege read access to CloudWatch, Performance
  Insights, RDS, the DB secret, SNS, and invoke rights on the gateway plus tool Lambdas.
- **Agent Space roles**: `DevOpsAgentRole-AgentSpace` (assumed by the service to
  monitor the account) and `DevOpsAgentRole-WebappAdmin` (backs the operator web app).

### AgentCore MCP gateway

- **`dbops-mcp-gateway`**: an MCP gateway with **AWS IAM / SigV4** inbound auth.
- **Gateway target**: registers the query Lambda behind the gateway with all
  **13 inline tool schemas**, so any MCP client discovers the tools.

### DevOps Agent space and integration

- **Agent space `sql-server-dbops`** with the **operator web app enabled** (IAM auth).
- **AWS account association** (monitor): lets the agent read your account via the
  agent-space role.
- **MCP service registration and 13-tool allowlist**: registers the gateway as a
  SigV4 MCP service and allowlists every tool for the agent to call.

### Assets (agent knowledge)

- **`sql-server-investigation` skill**: the triage, diagnose, drill-down, correlate,
  and recommend methodology (SKILL.md plus a reference doc), inlined into the
  template and created via the Asset API.
- **`agents_md` instructions**: always-applied directives telling the agent to use
  the SQL Server skill for RDS SQL Server investigations.

### Event-driven alarm plumbing

- **Webhook secret** (`dbops-devops-agent-webhook`): created as a container with
  placeholder values that you populate in Step 2.
- **Three demo CloudWatch alarms** (`HighCPU`, `HighConnections`, `HighReadLatency`)
  on the RDS instance, each wired to invoke the webhook executor so a breach
  auto-starts an investigation.

**The one manual step:** minting the webhook URL and secret (Step 2) is console-only.
CloudFormation cannot generate the HMAC key pair, so the stack creates the secret
with placeholder values that you populate afterward.

## Prerequisites

### Tooling

- **AWS CLI v2** (any current version).
- **Python 3** — used by `deploy.sh` to regenerate the skill assets and build the
  deploy parameters (no `jq` required).

### Base infrastructure (deploy this first)

This stack **references** an existing RDS SQL Server environment; it does not create
one. Deploy [`templates/infrastructure.yaml`](../../templates/infrastructure.yaml)
first (VPC, RDS SQL Server, secret, SNS). Its outputs feed `parameters.json` below.

```bash
aws cloudformation deploy \
  --template-file ../../templates/infrastructure.yaml \
  --stack-name dbops --capabilities CAPABILITY_NAMED_IAM --region us-west-2
```

### Artifact S3 bucket

`cloudformation package` (Step 1) **uploads** the pymssql layer and the three Lambda
code bundles into an S3 bucket and rewrites the template to point at them. You do
**not** copy anything into the bucket yourself. You only need to supply the name of
an existing bucket in the same region. Create one (or reuse any bucket you own):

```bash
export AWS_REGION=us-west-2
export YOUR_ARTIFACT_BUCKET="dbops-devops-agent-artifacts-$(aws sts get-caller-identity --query Account --output text)-$AWS_REGION"

aws s3api create-bucket --bucket "$YOUR_ARTIFACT_BUCKET" --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" 2>/dev/null || true
```

### Deploy permissions

If you deploy as an admin (or any identity with the needed permissions), **skip this
section**. No `--role-arn` is required.

**Optional least-privilege deploy role.** If you can't (or don't want to) deploy as an
admin, deploy [`cfn-service-role.yaml`](cfn-service-role.yaml) first and export its ARN.
It grants only the specific actions this stack needs. If you skip this, leave
`CFN_ROLE_ARN` unset (the deploy command omits `--role-arn` automatically):

```bash
aws cloudformation deploy \
  --template-file cfn-service-role.yaml \
  --stack-name dbops-devops-agent-cfn-role \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION"

# Run this export ONLY after the stack above exists:
export CFN_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name dbops-devops-agent-cfn-role --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" --output text)
```

### Build parameters.json from the base stack outputs

The six parameters (RDS instance, DB secret ARN, SNS topic, security group, two
subnets) all come from the `dbops` base stack. View them with:

```bash
aws cloudformation describe-stacks --stack-name dbops --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs' --output table
```

Copy [`parameters.example.json`](parameters.example.json) to `parameters.json` and
fill in each `ParameterValue` from those outputs
(`DBInstanceId`, `DBSecretId` into `DBSecretArn`, `SNSTopicName`, `SecurityGroupId`,
`Subnet1`, `Subnet2`):

```bash
cp parameters.example.json parameters.json
# edit parameters.json, replacing the placeholders with your dbops outputs
```

## Step 1: Deploy

Run [`deploy.sh`](deploy.sh) from `deployment/devops-agent/`. It regenerates the skill
assets from source, packages the Lambda/layer artifacts, and deploys the stack in one
command:

```bash
cd deployment/devops-agent    # from the repo root
export AWS_REGION=us-west-2
export YOUR_ARTIFACT_BUCKET=<your-bucket>       # see "Artifact S3 bucket" above
export CFN_ROLE_ARN="$CFN_ROLE_ARN"             # optional; omit to deploy as yourself

./deploy.sh
```

`deploy.sh` reads parameters from `parameters.json`, prints the stack outputs (gateway
URL, agent space ID, webhook secret ARN) when done, and needs only the AWS CLI and
Python 3 (no `jq`).

> **IAM propagation.** The MCP service registration depends on the signing role's
> trust and invoke-gateway grant. If the deploy fails once on an authorization error
> for `McpService`, re-run `./deploy.sh`. IAM is just catching up.

### Customizing the investigation skill

The skill is your DBA methodology, and it is the piece you are most likely to change.
Edit the Markdown source, **not** the template:

- [`skills/sql-server-investigation/SKILL.md`](skills/sql-server-investigation/SKILL.md)
- [`skills/sql-server-investigation/references/tool-reference.md`](skills/sql-server-investigation/references/tool-reference.md)
- [`AGENTS.md`](AGENTS.md)

`deploy.sh` runs [`build_skill_assets.py`](build_skill_assets.py) first, which injects
those files into the `SkillAsset`/`AgentsMdAsset` resources in `dbops-devops-agent.yaml`
(between `BEGIN/END GENERATED ASSETS` markers). Those template blocks are generated —
do not hand-edit them; your changes there would be overwritten on the next deploy.

## Step 2: Mint and store the webhook credentials (manual)

This is the only step CloudFormation cannot do.

1. Open the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
2. Click **sql-server-dbops**, then **Capabilities**, **Webhooks**, **Agent Space Webhook**, **Add**
3. Copy the generated **Webhook URL** and **Secret Key**
4. Write them into the secret the stack created:

```bash
aws secretsmanager put-secret-value \
  --secret-id dbops-devops-agent-webhook \
  --secret-string "{\"webhookUrl\":\"<paste URL>\",\"webhookSecret\":\"<paste secret>\"}" \
  --region "$AWS_REGION"
```

The alarms and executor Lambda are already wired. Once the secret holds real values,
alarm-triggered investigations work.

## Step 3: Verify

**Open the web app first.** Either use the [DevOps Agent console](https://console.aws.amazon.com/aidevops/home#/agent-spaces)
(pick **sql-server-dbops**), or get the direct URL:

```bash
aws devops-agent get-agent-space --agent-space-id <AgentSpaceId from Step 1 outputs> \
  --region "$AWS_REGION" --query 'agentSpace.operatorApp.operatorAppUrl' --output text
```

### Test the integration (alarm-triggered)

Invoke the alarm manually to verify end-to-end:

```bash
aws cloudwatch set-alarm-state \
  --alarm-name "dbops-demo-HighCPU" \
  --state-value ALARM \
  --state-reason "Manual test of alarm-to-investigation flow" \
  --region "$AWS_REGION"
```

Within seconds, check the DevOps Agent Web App. A new investigation should appear,
triggered by the alarm. The agent uses the `sql-server-investigation` skill, reads
CloudWatch/Database Insights via its IAM role, and calls your MCP tools through the
Gateway when deeper SQL-level data is needed.

> The three demo alarm thresholds are intentionally low so they trip quickly.
> Raise them for production workloads.

### Start an investigation (manual)

Open the DevOps Agent Web App and try:

```
Give me a complete database health report
The database is experiencing high CPU. Diagnose the root cause.
Are there any blocking sessions affecting performance?
```

## Tool Reference

| Gateway Target | Tools | Data Sources |
|---------------|-------|-------------|
| `dbops-query-tools` (13) | Slow queries, blocking, Query Store, indexes, execution plans | SQL Server DMVs |

Tool names in DevOps Agent use the format `<target>___<tool>` (triple underscore).

> **Note:** the stack deploys only the SQL-level query tools. Host metrics (CPU,
> memory, connections, IOPS, latency, storage) are read by the DevOps Agent natively
> through CloudWatch and Performance Insights / Database Insights, so no health-tool
> Lambda is deployed. The `sql-server-investigation` skill uses those native APIs for
> triage and the MCP/Lambda tools for the SQL-level detail the agent cannot reach.

## Cleanup

```bash
aws cloudformation delete-stack --stack-name dbops-devops-agent --region "$AWS_REGION"
aws cloudformation wait stack-delete-complete --stack-name dbops-devops-agent --region "$AWS_REGION"
```

One stack delete removes the agent space, gateway, targets, service, associations,
assets, Lambdas, layer, roles, secret, and alarms. Delete the CFN service-role stack
too if you created one.
