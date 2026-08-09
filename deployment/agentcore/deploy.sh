#!/bin/bash
set -e
# This script lives in deployment/agentcore/. Repo-root assets (.env, .venv,
# db-engines/, scripts/, .bedrock_agentcore.yaml) are two levels up, via ROOT_DIR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.env" 2>/dev/null || true
source "$ROOT_DIR/.venv/bin/activate" 2>/dev/null || true

# ─────────────────────────────────────────────────────────────────
# Region resolution (single source of truth)
# Use AWS_REGION from .env; fall back to AWS_DEFAULT_REGION or us-east-1.
# Export BOTH so the agentcore CLI, AWS CLI, and boto3 all agree — otherwise
# the CLI can silently fall back to the profile default and deploy to the
# wrong region (e.g. subnet "not found" because it lives in another region).
# ─────────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_REGION
export AWS_DEFAULT_REGION="$AWS_REGION"
echo "🌎 Using region: $AWS_REGION"
echo ""

SQL_SERVER_DIR="$ROOT_DIR/db-engines/sql-server"

# Step 0: Create shared memory with semantic + summarization strategies
echo "🧠 Setting up shared memory..."
MEMORY_ID=$(python3 "$ROOT_DIR/scripts/setup_memory.py" | grep "^MEMORY_ID=" | cut -d= -f2)
if [ -z "$MEMORY_ID" ]; then
    echo "❌ Failed to create shared memory"
    exit 1
fi
echo ""

STAGE=$(mktemp -d)
trap "rm -rf $STAGE" EXIT

cp -r "$SQL_SERVER_DIR/config" "$STAGE/config"
cp -r "$SQL_SERVER_DIR/tools" "$STAGE/tools"
cp "$SQL_SERVER_DIR/requirements.txt" "$STAGE/"
for f in database_health_agent.py query_performance_agent.py security_audit_agent.py data_lifecycle_agent.py supervisor_agent.py; do
    cp "$SQL_SERVER_DIR/agents/$f" "$STAGE/"
done

cd "$STAGE"

COMMON="--deployment-type direct_code_deploy --non-interactive --disable-memory --vpc --subnets $SUBNET1 --security-groups $SECURITY_GROUP_ID --execution-role $AGENTCORE_ROLE_ARN"

# Pre-flight: detect stale agents from a different VPC/subnet
# When --auto-update-on-conflict changes VPC config, endpoints aren't recreated,
# leaving agents in READY state but unable to receive invocations.
echo "🔍 Checking for stale agents from a different VPC..."
STALE_AGENTS=$(python3 -c "
import boto3, json
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
names = ['database_health_agent','query_performance_agent','security_audit_agent','data_lifecycle_agent','supervisor_agent']
runtimes = client.list_agent_runtimes(maxResults=50).get('agentRuntimes', [])
for r in runtimes:
    if r['agentRuntimeName'] in names:
        rt = client.get_agent_runtime(agentRuntimeId=r['agentRuntimeId'])
        nc = rt.get('networkConfiguration', {}).get('networkModeConfig', {})
        subnets = nc.get('subnets', [])
        if '$SUBNET1' not in subnets:
            print(r['agentRuntimeId'])
" 2>/dev/null)

if [ -n "$STALE_AGENTS" ]; then
    echo "  ⚠️  Found agents deployed to a different subnet. Deleting stale agents..."
    echo "  (--auto-update-on-conflict doesn't recreate endpoints when VPC changes)"
    for STALE_ID in $STALE_AGENTS; do
        echo "  Deleting $STALE_ID..."
        python3 -c "
import boto3
boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION').delete_agent_runtime(agentRuntimeId='$STALE_ID')
print('  ✅ Delete requested')
" 2>/dev/null
    done

    # delete_agent_runtime is asynchronous: it returns immediately while the runtime
    # stays in DELETING state for up to a few minutes. Deploying before deletion
    # completes makes agentcore (with --auto-update-on-conflict) attempt
    # UpdateAgentRuntime on the dying runtime -> ConflictException ("... while it's
    # DELETING"). Wait until every stale runtime is fully gone before continuing.
    echo "  ⏳ Waiting for stale agents to finish deleting..."
    python3 -c "
import boto3, time, sys
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
pending = set('''$STALE_AGENTS'''.split())
deadline = time.time() + 600
while pending and time.time() < deadline:
    existing = {r['agentRuntimeId'] for r in client.list_agent_runtimes(maxResults=50).get('agentRuntimes', [])}
    gone = {rid for rid in pending if rid not in existing}
    for rid in sorted(gone):
        print(f'  ✅ {rid} deleted')
    pending -= gone
    if pending:
        time.sleep(10)
if pending:
    print(f'  ❌ Timed out waiting for: {sorted(pending)}', file=sys.stderr)
    sys.exit(1)
print('  ✅ All stale agents fully deleted')
"
    if [ $? -ne 0 ]; then
        echo "❌ Stale agents did not finish deleting in time. Re-run deploy shortly."
        exit 1
    fi
    echo ""
else
    echo "  ✅ No stale agents found"
    echo ""
fi

echo "🏥 [1/5] Database Health Agent..."
echo "agentcore configure --name database_health_agent -e database_health_agent.py ${COMMON}"

agentcore configure --name database_health_agent -e database_health_agent.py $COMMON
agentcore deploy --agent database_health_agent --auto-update-on-conflict \
  --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID \
  --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION
echo "✅ Database Health Agent deployed"

echo "⚡ [2/5] Query Performance Agent..."
agentcore configure --name query_performance_agent -e query_performance_agent.py $COMMON
agentcore deploy --agent query_performance_agent --auto-update-on-conflict \
  --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID \
  --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION
echo "✅ Query Performance Agent deployed"

echo "🔒 [3/5] Security Audit Agent..."
agentcore configure --name security_audit_agent -e security_audit_agent.py $COMMON
agentcore deploy --agent security_audit_agent --auto-update-on-conflict \
  --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID \
  --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION
echo "✅ Security Audit Agent deployed"

echo "💾 [4/5] Data Lifecycle Agent..."
agentcore configure --name data_lifecycle_agent -e data_lifecycle_agent.py $COMMON
agentcore deploy --agent data_lifecycle_agent --auto-update-on-conflict \
  --env MEMORY_ID=$MEMORY_ID --env DB_INSTANCE_ID=$DB_INSTANCE_ID \
  --env DB_SECRET_ID=$DB_SECRET_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION
echo "✅ Data Lifecycle Agent deployed"

echo "🎯 [5/5] Supervisor Agent..."
# Look up fresh sub-agent ARNs (they change on each deploy)
echo "  Resolving sub-agent ARNs..."
AGENT_ARNS=$(python3 -c "
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
runtimes = client.list_agent_runtimes(maxResults=50).get('agentRuntimes', [])
mapping = {'database_health_agent':'HEALTH', 'query_performance_agent':'PERFORMANCE', 'security_audit_agent':'SECURITY', 'data_lifecycle_agent':'LIFECYCLE'}
for r in runtimes:
    prefix = mapping.get(r['agentRuntimeName'])
    if prefix:
        print(f\"{prefix}_AGENT_ARN={r['agentRuntimeArn']}\")
")
eval "$AGENT_ARNS"
echo "  HEALTH_AGENT_ARN=$HEALTH_AGENT_ARN"
echo "  PERFORMANCE_AGENT_ARN=$PERFORMANCE_AGENT_ARN"
echo "  SECURITY_AGENT_ARN=$SECURITY_AGENT_ARN"
echo "  LIFECYCLE_AGENT_ARN=$LIFECYCLE_AGENT_ARN"
agentcore configure --name supervisor_agent -e supervisor_agent.py $COMMON
agentcore deploy --agent supervisor_agent --auto-update-on-conflict \
  --env MEMORY_ID=$MEMORY_ID --env SNS_TOPIC_NAME=$SNS_TOPIC_NAME --env AWS_REGION=$AWS_REGION \
  --env HEALTH_AGENT_ARN=$HEALTH_AGENT_ARN --env PERFORMANCE_AGENT_ARN=$PERFORMANCE_AGENT_ARN \
  --env SECURITY_AGENT_ARN=$SECURITY_AGENT_ARN --env LIFECYCLE_AGENT_ARN=$LIFECYCLE_AGENT_ARN
echo "✅ Supervisor Agent deployed"

# Update .env with fresh agent ARNs
echo "📝 Updating .env with new agent ARNs..."
ENV_FILE="$ROOT_DIR/.env"
ALL_ARNS=$(python3 -c "
import boto3
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
runtimes = client.list_agent_runtimes(maxResults=50).get('agentRuntimes', [])
mapping = {
    'database_health_agent': 'HEALTH_AGENT_ARN',
    'query_performance_agent': 'PERFORMANCE_AGENT_ARN',
    'security_audit_agent': 'SECURITY_AGENT_ARN',
    'data_lifecycle_agent': 'LIFECYCLE_AGENT_ARN',
    'supervisor_agent': 'SUPERVISOR_AGENT_ARN',
}
for r in runtimes:
    key = mapping.get(r['agentRuntimeName'])
    if key:
        print(f\"{key}={r['agentRuntimeArn']}\")
")

while IFS='=' read -r key value; do
    if grep -q "^export ${key}=" "$ENV_FILE"; then
        sed -i '' "s|^export ${key}=.*|export ${key}=${value}|" "$ENV_FILE"
    else
        echo "export ${key}=${value}" >> "$ENV_FILE"
    fi
done <<< "$ALL_ARNS"
echo "  ✅ .env updated"

# Generate .bedrock_agentcore.yaml so `agentcore invoke --agent <name>` works from project root
echo "📝 Generating .bedrock_agentcore.yaml..."
python3 -c "
import boto3, yaml
client = boto3.client('bedrock-agentcore-control', region_name='$AWS_REGION')
runtimes = client.list_agent_runtimes(maxResults=50).get('agentRuntimes', [])
names = ['database_health_agent','query_performance_agent','security_audit_agent','data_lifecycle_agent','supervisor_agent']
agents = {}
for r in runtimes:
    n = r['agentRuntimeName']
    if n in names:
        agents[n] = {
            'name': n,
            'entrypoint': n + '.py',
            'deployment_type': 'direct_code_deploy',
            'runtime_type': 'PYTHON_3_12',
            'platform': 'linux/arm64',
            'container_runtime': None,
            'source_path': '$ROOT_DIR',
            'aws': {
                'execution_role': '$AGENTCORE_ROLE_ARN',
                'execution_role_auto_create': True,
                'account': '${AWS_ACCOUNT_ID:-123456789012}',
                'region': '$AWS_REGION',
                'ecr_repository': None,
                'ecr_auto_create': False,
                's3_path': None,
                's3_auto_create': True,
                'network_configuration': {
                    'network_mode': 'VPC',
                    'network_mode_config': {
                        'security_groups': ['$SECURITY_GROUP_ID'],
                        'subnets': ['$SUBNET1'],
                    },
                },
                'protocol_configuration': {'server_protocol': 'HTTP'},
                'observability': {'enabled': True},
                'lifecycle_configuration': {'idle_runtime_session_timeout': None, 'max_lifetime': None},
            },
            'bedrock_agentcore': {
                'agent_id': r['agentRuntimeId'],
                'agent_arn': r['agentRuntimeArn'],
                'agent_session_id': None,
            },
            'codebuild': {'project_name': None, 'execution_role': None, 'source_bucket': None},
            'memory': {
                'mode': 'NO_MEMORY',
                'memory_id': None, 'memory_arn': None, 'memory_name': None,
                'event_expiry_days': 30,
                'first_invoke_memory_check_done': False,
                'was_created_by_toolkit': False,
            },
            'identity': {'credential_providers': [], 'workload': None},
            'aws_jwt': {'enabled': False, 'audiences': [], 'signing_algorithm': 'ES384', 'issuer_url': None, 'duration_seconds': 300},
            'authorizer_configuration': None,
            'request_header_configuration': None,
            'oauth_configuration': None,
            'api_key_env_var_name': None,
            'api_key_credential_provider_name': None,
            'is_generated_by_agentcore_create': False,
        }
config = {'default_agent': 'supervisor_agent', 'agents': agents}
with open('$ROOT_DIR/.bedrock_agentcore.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
print('  ✅ .bedrock_agentcore.yaml generated')
"
echo ""
echo "🎉 All 5 agents deployed to private subnet: $SUBNET1"
