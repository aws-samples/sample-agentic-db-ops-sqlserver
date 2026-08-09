# Updated: 2026-03-15
#!/bin/bash
# deploy_all_agents.sh - Deploy all 5 database agents to AgentCore Runtime

set -e  # Exit on error

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🚀 Autonomous DBOps — Full Agent Deployment Suite        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Verify environment variables
if [ -z "$AGENTCORE_ROLE_ARN" ] || [ -z "$SUBNET1" ] || [ -z "$SECURITY_GROUP_ID" ]; then
    echo "❌ Environment variables not set. Please ensure all variables are exported."
    exit 1
fi

# ─────────────────────────────────────────────────────────────────
# STEP 1: Create shared memory for all agents
# ─────────────────────────────────────────────────────────────────
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🧠 Step 1: Creating shared memory for all agents            │"
echo "│     Strategy: semanticMemoryStrategy + summaryMemoryStrategy │"
echo "│     Retention: 30 days                                       │"
echo "└──────────────────────────────────────────────────────────────┘"
agentcore memory create dbops_shared_memory \
  --strategies '[{"semanticMemoryStrategy": {"name": "dbops_facts"}}, {"summaryMemoryStrategy": {"name": "dbops_summaries"}}]' \
  --event-expiry-days 30 \
  --region $AWS_REGION \
  --wait
MEMORY_ID=$(agentcore memory list --region $AWS_REGION 2>/dev/null | grep dbops_shared_memory | awk '{print $4}')
echo "✅ Shared memory ready: $MEMORY_ID"
echo ""

# Common configure flags to skip all interactive prompts
COMMON_FLAGS="--deployment-type direct_code_deploy --non-interactive --disable-memory --region $AWS_REGION --vpc --subnets $SUBNET1,$SUBNET2 --security-groups $SECURITY_GROUP_ID --execution-role $AGENTCORE_ROLE_ARN"

# ─────────────────────────────────────────────────────────────────
# STEP 2: Deploy all 5 agents
# ─────────────────────────────────────────────────────────────────
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  📦 Step 2: Deploying all agents to AgentCore Runtime        │"
echo "└──────────────────────────────────────────────────────────────┘"

echo "  📊 [1/5] Database Health Agent..."
agentcore configure --name database_health_agent -e database_health_agent.py $COMMON_FLAGS
agentcore deploy --agent database_health_agent --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION --env AGENT_OBSERVABILITY_ENABLED=true
echo "  ✅ Database Health Agent deployed"
echo ""

echo "  ⚡ [2/5] Query Performance Agent..."
agentcore configure --name query_performance_agent -e query_performance_agent.py $COMMON_FLAGS
agentcore deploy --agent query_performance_agent --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION --env AGENT_OBSERVABILITY_ENABLED=true
echo "  ✅ Query Performance Agent deployed"
echo ""

echo "  🔒 [3/5] Security Audit Agent..."
agentcore configure --name security_audit_agent -e security_audit_agent.py $COMMON_FLAGS
agentcore deploy --agent security_audit_agent --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION --env AGENT_OBSERVABILITY_ENABLED=true
echo "  ✅ Security Audit Agent deployed"
echo ""

echo "  💾 [4/5] Data Lifecycle Agent..."
agentcore configure --name data_lifecycle_agent -e data_lifecycle_agent.py $COMMON_FLAGS
agentcore deploy --agent data_lifecycle_agent --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION --env AGENT_OBSERVABILITY_ENABLED=true
echo "  ✅ Data Lifecycle Agent deployed"
echo ""

# ─────────────────────────────────────────────────────────────────
# STEP 3: Extract agent ARNs for Supervisor
# ─────────────────────────────────────────────────────────────────
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔗 Step 3: Extracting agent ARNs for Supervisor             │"
echo "└──────────────────────────────────────────────────────────────┘"

echo "  ⏳ Waiting for agents to be ready..."
sleep 10

MAX_RETRIES=5
RETRY_DELAY=5

extract_arn() {
    local agent_name=$1
    local retries=0
    local arn=""
    
    while [ $retries -lt $MAX_RETRIES ]; do
        arn=$(agentcore status --agent $agent_name --verbose 2>/dev/null | grep -o '"agent_arn": "[^"]*"' | head -1 | cut -d'"' -f4)
        
        if [ -n "$arn" ]; then
            echo "$arn"
            return 0
        fi
        
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            echo "    Retry $retries/$MAX_RETRIES for $agent_name..." >&2
            sleep $RETRY_DELAY
        fi
    done
    
    return 1
}

export HEALTH_AGENT_ARN=$(extract_arn database_health_agent)
export PERFORMANCE_AGENT_ARN=$(extract_arn query_performance_agent)
export SECURITY_AGENT_ARN=$(extract_arn security_audit_agent)
export LIFECYCLE_AGENT_ARN=$(extract_arn data_lifecycle_agent)

echo "  HEALTH:      $HEALTH_AGENT_ARN"
echo "  PERFORMANCE: $PERFORMANCE_AGENT_ARN"
echo "  SECURITY:    $SECURITY_AGENT_ARN"
echo "  LIFECYCLE:   $LIFECYCLE_AGENT_ARN"
echo ""

# Validate ARNs
VALIDATION_FAILED=0
for VAR_NAME in HEALTH_AGENT_ARN PERFORMANCE_AGENT_ARN SECURITY_AGENT_ARN LIFECYCLE_AGENT_ARN; do
  if [ -z "${!VAR_NAME}" ]; then
    echo "  ❌ Failed to extract $VAR_NAME"
    VALIDATION_FAILED=1
  fi
done

if [ $VALIDATION_FAILED -eq 1 ]; then
    echo ""
    echo "❌ ARN validation failed. Cannot deploy Supervisor Agent."
    exit 1
fi
echo "  ✅ All ARNs validated"
echo ""

echo "  🎯 [5/5] Supervisor Agent..."
agentcore configure --name supervisor_agent -e supervisor_agent.py $COMMON_FLAGS
agentcore deploy --agent supervisor_agent --env MEMORY_ID=$MEMORY_ID \
  --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME \
  --env AWS_REGION=$AWS_REGION \
  --env HEALTH_AGENT_ARN=$HEALTH_AGENT_ARN \
  --env PERFORMANCE_AGENT_ARN=$PERFORMANCE_AGENT_ARN \
  --env SECURITY_AGENT_ARN=$SECURITY_AGENT_ARN \
  --env LIFECYCLE_AGENT_ARN=$LIFECYCLE_AGENT_ARN \
  --env AGENT_OBSERVABILITY_ENABLED=true
echo "  ✅ Supervisor Agent deployed"
echo ""

# ─────────────────────────────────────────────────────────────────
# STEP 4: Validate deployment
# ─────────────────────────────────────────────────────────────────
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔍 Step 4: Validating deployment                            │"
echo "└──────────────────────────────────────────────────────────────┘"

for AGENT in database_health_agent query_performance_agent security_audit_agent data_lifecycle_agent supervisor_agent; do
  STATUS=$(agentcore status --agent $AGENT 2>/dev/null | grep -o "READY\|FAILED\|CREATING" | head -1)
  echo "  ${STATUS:-❓} $AGENT"
done
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🎉 All 5 agents deployed with shared memory!                ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  📊 Status:  agentcore status                                ║"
echo "║  🧪 Test:    agentcore invoke --agent supervisor_agent \     ║"
echo "║              '{\"prompt\": \"Give me a health report\"}'     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
