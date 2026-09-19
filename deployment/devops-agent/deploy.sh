#!/usr/bin/env bash
# Deploy the DevOps Agent integration in one command.
# Regenerates the skill/agents_md Assets from source (skills/ + AGENTS.md),
# packages the Lambda/layer artifacts, and deploys the CloudFormation stack.
#
# Required env:
#   AWS_REGION            e.g. us-west-2
#   YOUR_ARTIFACT_BUCKET  existing S3 bucket in AWS_REGION for `cfn package`
# Optional env:
#   CFN_ROLE_ARN          scoped deploy role ARN (from cfn-service-role.yaml)
#   STACK_NAME            default: dbops-devops-agent
#   PARAMS_FILE           default: parameters.json
set -euo pipefail
cd "$(dirname "$0")"

: "${AWS_REGION:?set AWS_REGION (e.g. us-west-2)}"
: "${YOUR_ARTIFACT_BUCKET:?set YOUR_ARTIFACT_BUCKET (an existing S3 bucket in AWS_REGION)}"
STACK="${STACK_NAME:-dbops-devops-agent}"
PARAMS="${PARAMS_FILE:-parameters.json}"

echo "==> Regenerating skill assets from source files"
python3 build_skill_assets.py

echo "==> Packaging Lambda/layer artifacts to s3://$YOUR_ARTIFACT_BUCKET"
aws cloudformation package \
  --template-file dbops-devops-agent.yaml \
  --s3-bucket "$YOUR_ARTIFACT_BUCKET" \
  --output-template-file packaged.yaml \
  --region "$AWS_REGION"

# Build inline Key=Value parameter overrides from parameters.json (no jq needed).
PARAM_OVERRIDES=$(python3 -c "import json; print(' '.join(f'{p[\"ParameterKey\"]}={p[\"ParameterValue\"]}' for p in json.load(open('$PARAMS'))))")

# Optional scoped deploy role, passed as an array so the greedy
# --parameter-overrides (kept last) cannot swallow it.
ROLE_ARGS=()
[ -n "${CFN_ROLE_ARN:-}" ] && ROLE_ARGS=(--role-arn "$CFN_ROLE_ARN")

echo "==> Deploying stack: $STACK"
aws cloudformation deploy \
  --template-file packaged.yaml \
  --stack-name "$STACK" \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  ${ROLE_ARGS[@]+"${ROLE_ARGS[@]}"} \
  --parameter-overrides $PARAM_OVERRIDES

echo "==> Done. Stack outputs:"
aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs' --output table
