# Configuration

All configuration lives in `settings.py`. Values are read from environment variables with sensible defaults.

## Environment Variables

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_INSTANCE_ID` | `dbops-infra-sqlserver` | RDS instance identifier |
| `DB_SECRET_ID` | `dbops-infra-sqlserver-secret` | Secrets Manager secret name for DB credentials |

### AWS

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-west-2` | AWS region |
| `SNS_TOPIC_NAME` | `sqlserver-database-alerts` | SNS topic for alert notifications |

### Bedrock

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | LLM model for agent reasoning |

### AgentCore Memory

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_ID` | *(empty)* | AgentCore Memory resource ID. When set, enables cross-session knowledge retention. When empty, agents work without memory. |

### AgentCore Deployment (VPC)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTCORE_ROLE_ARN` | *(empty)* | IAM execution role ARN for AgentCore Runtime |
| `SECURITY_GROUP_ID` | *(empty)* | VPC security group for agent containers |
| `SUBNET1` | *(empty)* | Private subnet 1 (agent containers) |
| `SUBNET2` | *(empty)* | Private subnet 2 (agent containers) |

### Supervisor Agent ARNs

Set automatically by `deploy.sh` after deploying the 4 sub-agents.

| Variable | Description |
|----------|-------------|
| `HEALTH_AGENT_ARN` | Database Health Agent runtime ARN |
| `PERFORMANCE_AGENT_ARN` | Query Performance Agent runtime ARN |
| `SECURITY_AGENT_ARN` | Security Audit Agent runtime ARN |
| `LIFECYCLE_AGENT_ARN` | Data Lifecycle Agent runtime ARN |

## VPC Endpoint Services

AgentCore agents run in private subnets. These VPC endpoints are required for agents to reach AWS services without a NAT gateway.

### Required (Interface — port 443)

| Service | Endpoint | Used By |
|---------|----------|---------|
| Bedrock Runtime | `com.amazonaws.{region}.bedrock-runtime` | All agents (LLM inference) |
| Bedrock AgentCore | `com.amazonaws.{region}.bedrock-agentcore` | All agents (runtime + A2A) |
| AgentCore Control | `com.amazonaws.{region}.bedrock-agentcore-control` | All agents (control plane communication) |
| AgentCore Gateway | `com.amazonaws.{region}.bedrock-agentcore.gateway` | All agents (invocation routing) |
| Secrets Manager | `com.amazonaws.{region}.secretsmanager` | Query Perf, Security, Data Lifecycle (DB credentials) |
| RDS | `com.amazonaws.{region}.rds` | Health, Security, Data Lifecycle (describe instances, events) |
| CloudWatch Monitoring | `com.amazonaws.{region}.monitoring` | Health, Data Lifecycle (get_metric_statistics) |
| CloudWatch Logs | `com.amazonaws.{region}.logs` | Security (failed logins, Insights queries) |
| ECR Docker | `com.amazonaws.{region}.ecr.dkr` | All agents (container image pull) |
| ECR API | `com.amazonaws.{region}.ecr.api` | All agents (auth token) |

### Required (Gateway)

| Service | Endpoint | Used By |
|---------|----------|---------|
| S3 | `com.amazonaws.{region}.s3` | All agents (ECR image layers) |

### Recommended (Interface — needed by specific agents)

| Service | Endpoint | Used By |
|---------|----------|---------|
| Database Insights | `com.amazonaws.{region}.pi` | Database Health Agent |
| SNS | `com.amazonaws.{region}.sns` | All agents (alert notifications) |
| CloudTrail | `com.amazonaws.{region}.cloudtrail` | Security Audit Agent |
| KMS | `com.amazonaws.{region}.kms` | Database Health Agent (decrypt PI data) |
| STS | `com.amazonaws.{region}.sts` | Credential refresh + cross-account |

### Security Group for VPC Endpoints

- Inbound: TCP 443 from VPC CIDR
- Outbound: All traffic
