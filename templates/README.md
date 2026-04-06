# Templates

CloudFormation templates and IAM policy documents for infrastructure setup.

## Two IAM Roles Required

| Role | Who Uses It | Purpose |
|------|-------------|---------|
| **AgentCore Execution Role** | AgentCore Runtime (cloud) | Assumed by agents to call AWS services (Bedrock, RDS, CloudWatch, etc.) |
| **Operator Role** | You / your server / CI/CD | Assumed by the person running `agentcore deploy`, `agentcore invoke`, and `./deploy.sh` |

---

## 1. AgentCore Execution Role

The role that AgentCore Runtime assumes to run your agents.

### Option A: CloudFormation (recommended)

```bash
aws cloudformation deploy \
  --template-file templates/agentcore-role.yaml \
  --stack-name dbops-agentcore-role \
  --capabilities CAPABILITY_NAMED_IAM

export AGENTCORE_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name dbops-agentcore-role \
  --query 'Stacks[0].Outputs[?OutputKey==`RoleArn`].OutputValue' \
  --output text)
```

### Option B: AWS CLI

```bash
aws iam create-role \
  --role-name AgentCoreDBOpsRole \
  --assume-role-policy-document file://templates/agentcore-trust-policy.json

aws iam put-role-policy \
  --role-name AgentCoreDBOpsRole \
  --policy-name AgentCoreDBOpsPolicy \
  --policy-document file://templates/agentcore-policy.json

aws iam attach-role-policy \
  --role-name AgentCoreDBOpsRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess

export AGENTCORE_ROLE_ARN=$(aws iam get-role --role-name AgentCoreDBOpsRole --query 'Role.Arn' --output text)
```

---

## 2. Operator Role

The permissions needed on the machine where you run `deploy.sh` and `agentcore invoke`. Attach `operator-policy.json` to your IAM user, role, or instance profile.

```bash
# For an IAM user
aws iam put-user-policy \
  --user-name your-username \
  --policy-name DBOpsOperatorPolicy \
  --policy-document file://templates/operator-policy.json

# For an EC2 instance role
aws iam put-role-policy \
  --role-name your-instance-role \
  --policy-name DBOpsOperatorPolicy \
  --policy-document file://templates/operator-policy.json
```

---

## Files

| File | Description |
|------|-------------|
| `agentcore-role.yaml` | CloudFormation — creates the AgentCore execution role + inline policy |
| `agentcore-trust-policy.json` | Trust policy — allows `bedrock-agentcore.amazonaws.com` to assume the role |
| `agentcore-policy.json` | AgentCore execution policy — what agents can do (Bedrock, RDS, CloudWatch, etc.) |
| `operator-policy.json` | Operator policy — what you need to deploy and invoke agents |

## AgentCore Execution Role — Permissions

| Sid | Actions | Used By |
|-----|---------|---------|
| BedrockModelInvocation | `bedrock:InvokeModel`, `InvokeModelWithResponseStream` | All agents |
| AgentCoreA2AInvocation | `bedrock-agentcore:InvokeAgentRuntime` | Supervisor |
| PerformanceInsights (Database Insights) | `pi:GetResourceMetrics`, `DescribeDimensionKeys`, `GetDimensionKeyDetails` | Database Health |
| KMSDecryptForPI | `kms:Decrypt`, `DescribeKey` (scoped via `kms:ViaService` condition) | Database Health |
| CloudWatchMetrics | `cloudwatch:GetMetricStatistics`, `GetMetricData`, `ListMetrics`, `DescribeAlarms` | Health, Lifecycle |
| RDSReadOnly | `rds:Describe*` (6 specific actions) | Health, Security, Lifecycle |
| SecretsManagerDBCredentials | `secretsmanager:GetSecretValue` | Query Perf, Security, Lifecycle |
| SNSPublishAlerts | `sns:Publish`, `ListTopics` | All agents |
| CloudWatchLogsQuery | `logs:StartQuery`, `GetQueryResults`, `StopQuery` (scoped to `/aws/rds/*`) | Security |
| CloudWatchLogsAgentLogging | `logs:CreateLogGroup`, `CreateLogStream`, `PutLogEvents` (scoped to `/aws/bedrock-agentcore/*`) | All agents |
| CloudTrailLookup | `cloudtrail:LookupEvents` | Security |
| AgentCoreMemory | 7 memory actions (scoped to `memory/*`) | All agents |
| ECRContainerPull | ECR auth + image pull | All agents |
| OpenTelemetryTracing | `xray:PutTraceSegments`, `PutTelemetryRecords` | All agents |

## Operator Role — Permissions

| Sid | Actions | Purpose |
|-----|---------|---------|
| AgentCoreManagement | Create, update, delete, get, list, invoke agent runtimes | `agentcore deploy`, `agentcore invoke`, `agentcore status` |
| AgentCoreMemoryManagement | Create, delete, get, list memories | `agentcore memory create`, `agentcore memory list` |
| ECRRepositoryManagement | Create repo, push/pull images | Agent container image build and push |
| PassRoleToAgentCore | `iam:PassRole` (scoped to AgentCoreDBOpsRole + condition) | Pass execution role during deployment |
| IAMReadForValidation | `iam:GetRole` | Validate role exists before deploy |
| CloudWatchLogsForDeployment | Create log group, put resource policy | Agent log group setup |
| VPCReadForDeployment | Describe VPCs, subnets, security groups | VPC configuration validation |
| CloudFormationForIAMSetup | Stack operations (scoped to `dbops-agentcore-role/*`) | Deploy the execution role via CFN |
