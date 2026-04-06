import os

# ===== DATABASE =====
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')

# ===== AWS =====
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')

# ===== BEDROCK =====
LLM_MODEL = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')

# ===== AGENTCORE MEMORY =====
MEMORY_ID = os.getenv('MEMORY_ID', '')

# ===== AGENTCORE DEPLOYMENT =====
AGENTCORE_ROLE_ARN = os.getenv('AGENTCORE_ROLE_ARN', '')
SECURITY_GROUP_ID = os.getenv('SECURITY_GROUP_ID', '')
SUBNET1 = os.getenv('SUBNET1', '')
SUBNET2 = os.getenv('SUBNET2', '')

# ===== SUPERVISOR AGENT ARNS (set after deploying the 4 sub-agents) =====
HEALTH_AGENT_ARN = os.getenv('HEALTH_AGENT_ARN', '')
PERFORMANCE_AGENT_ARN = os.getenv('PERFORMANCE_AGENT_ARN', '')
SECURITY_AGENT_ARN = os.getenv('SECURITY_AGENT_ARN', '')
LIFECYCLE_AGENT_ARN = os.getenv('LIFECYCLE_AGENT_ARN', '')

# ===== VPC ENDPOINT SERVICES =====
# AgentCore agents run in private subnets. These VPC endpoints are required
# for agents to reach AWS services without a NAT gateway.
#
# Required VPC Endpoints (Interface - port 443):
#   com.amazonaws.{region}.bedrock-runtime       — LLM inference (Claude)
#   com.amazonaws.{region}.bedrock-agentcore     — AgentCore Runtime + A2A invocation
#   com.amazonaws.{region}.bedrock-agentcore-control — AgentCore control plane (agent ↔ control plane)
#   com.amazonaws.{region}.bedrock-agentcore.gateway — AgentCore gateway (invocation routing)
#   com.amazonaws.{region}.secretsmanager        — Database credentials
#   com.amazonaws.{region}.rds                   — RDS API (describe instances, events, snapshots)
#   com.amazonaws.{region}.monitoring            — CloudWatch metrics (get_metric_statistics)
#   com.amazonaws.{region}.logs                  — CloudWatch Logs (failed logins, Insights queries)
#   com.amazonaws.{region}.ecr.dkr              — ECR Docker image pull (agent container)
#   com.amazonaws.{region}.ecr.api              — ECR API (auth token)
#
# Required VPC Endpoints (Gateway):
#   com.amazonaws.{region}.s3                    — S3 (ECR image layers, logs)
#
# Recommended VPC Endpoints (Interface - needed by specific agents):
#   com.amazonaws.{region}.pi                    — Database Insights (Database Health Agent)
#   com.amazonaws.{region}.sns                   — SNS notifications (all agents)
#   com.amazonaws.{region}.cloudtrail            — CloudTrail lookups (Security Audit Agent)
#   com.amazonaws.{region}.kms                   — KMS decrypt (Database Insights data)
#   com.amazonaws.{region}.sts                   — STS (credential refresh + cross-account)
#
# Security Group for VPC Endpoints:
#   Inbound: TCP 443 from VPC CIDR
#   Outbound: All traffic
