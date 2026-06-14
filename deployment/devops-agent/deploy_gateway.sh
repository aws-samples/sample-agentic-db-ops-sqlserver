#!/bin/bash
# deploy_gateway.sh - Deploy SQL Server diagnostic tools as MCP endpoints via AgentCore Gateway
#
# Creates 2 Lambda functions (health + query tools) and an AgentCore Gateway with
# AWS IAM (SigV4) auth and all tools registered. Outputs gateway_config.json.
#
# Prerequisites:
#   - .env sourced (SUBNET1, SECURITY_GROUP_ID, AGENTCORE_ROLE_ARN, DB_SECRET_ID, DB_INSTANCE_ID, AWS_REGION, SNS_TOPIC_NAME)
#   - bedrock-agentcore-starter-toolkit installed
#   - pymssql Lambda layer available (pymssql-layer-3.12.zip)
#
# Usage:
#   ./deploy_gateway.sh           # Deploy
#   ./deploy_gateway.sh --cleanup # Remove everything

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/../.."

source "$ROOT_DIR/.env"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🌐 AgentCore Gateway — MCP Endpoint Deployment             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Cleanup mode
if [ "$1" == "--cleanup" ]; then
    echo "🧹 Cleaning up Gateway resources..."
    python3 "$SCRIPT_DIR/setup_gateway.py" --cleanup
    echo "  Deleting Lambda functions..."
    aws lambda delete-function --function-name dbops-health-tools --region $AWS_REGION 2>/dev/null || true
    aws lambda delete-function --function-name dbops-query-tools --region $AWS_REGION 2>/dev/null || true
    echo "  Deleting Lambda layer..."
    LAYER_VERSION=$(aws lambda list-layer-versions --layer-name pymssql-layer --region $AWS_REGION --query 'LayerVersions[0].Version' --output text 2>/dev/null || echo "")
    if [ -n "$LAYER_VERSION" ] && [ "$LAYER_VERSION" != "None" ]; then
        aws lambda delete-layer-version --layer-name pymssql-layer --version-number $LAYER_VERSION --region $AWS_REGION
    fi
    rm -f "$SCRIPT_DIR/gateway_config.json"
    echo "✅ Cleanup complete"
    exit 0
fi

# Validate environment
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔍 Validating environment                                    │"
echo "└──────────────────────────────────────────────────────────────┘"
for var in AWS_REGION SUBNET1 SECURITY_GROUP_ID AGENTCORE_ROLE_ARN DB_SECRET_ID DB_INSTANCE_ID SNS_TOPIC_NAME; do
    if [ -z "${!var}" ]; then
        echo "  ❌ $var is not set"
        exit 1
    fi
    echo "  ✅ $var=${!var}"
done
echo ""

# Publish pymssql Lambda layer
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  📦 Publishing pymssql Lambda layer                           │"
echo "└──────────────────────────────────────────────────────────────┘"
if [ ! -f "$SCRIPT_DIR/pymssql-layer-3.12.zip" ]; then
    echo "  ⚠️  pymssql-layer-3.12.zip not found. Building..."
    pip install pymssql -t /tmp/pymssql-layer/python --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -q
    cd /tmp/pymssql-layer && zip -r "$SCRIPT_DIR/pymssql-layer-3.12.zip" python -q && cd "$SCRIPT_DIR"
    rm -rf /tmp/pymssql-layer
fi
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name pymssql-layer \
    --compatible-runtimes python3.12 \
    --zip-file fileb://$SCRIPT_DIR/pymssql-layer-3.12.zip \
    --region $AWS_REGION \
    --query 'LayerVersionArn' --output text)
echo "  ✅ Layer: $LAYER_ARN"
echo ""

# Package Lambda functions
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  📦 Packaging Lambda functions                                │"
echo "└──────────────────────────────────────────────────────────────┘"
# Package Lambda functions from the self-contained lambda/<func>/ directories.
# Each dir already includes lambda_function.py + tools + shared_utils.py + config/,
# so we zip them directly (matches SETUP.md).
LAMBDA_DIR="$SCRIPT_DIR/lambda"

# Health tools Lambda
cd "$LAMBDA_DIR/health" && zip -r "$SCRIPT_DIR/health-tools.zip" . -q && cd "$SCRIPT_DIR"

# Query tools Lambda
cd "$LAMBDA_DIR/query" && zip -r "$SCRIPT_DIR/query-tools.zip" . -q && cd "$SCRIPT_DIR"
echo "  ✅ health-tools.zip"
echo "  ✅ query-tools.zip"
echo ""

# Ensure the execution role can be used by Lambda.
# AGENTCORE_ROLE_ARN is created trusting only bedrock-agentcore.amazonaws.com.
# Lambda also needs to assume it (lambda.amazonaws.com), and VPC-attached Lambdas
# need ENI permissions (AWSLambdaVPCAccessExecutionRole). Make this idempotent.
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔐 Preparing execution role for Lambda                       │"
echo "└──────────────────────────────────────────────────────────────┘"
ROLE_NAME="${AGENTCORE_ROLE_ARN##*/}"
aws iam update-assume-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["bedrock-agentcore.amazonaws.com","lambda.amazonaws.com"]},"Action":"sts:AssumeRole"}]}'
echo "  ✅ Trust policy allows lambda.amazonaws.com"
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole 2>/dev/null || true
echo "  ✅ AWSLambdaVPCAccessExecutionRole attached"

# With AWS_IAM gateway auth, targets use credentialProviderType=GATEWAY_IAM_ROLE,
# so the Gateway invokes the Lambdas AS this execution role. That requires an
# identity-based lambda:InvokeFunction grant on the role (the resource-based
# add-permission below covers the service-principal path, not the role path).
ACCOUNT_ID="${AGENTCORE_ROLE_ARN#arn:aws:iam::}"; ACCOUNT_ID="${ACCOUNT_ID%%:*}"
aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name GatewayInvokeDbopsLambdas \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"lambda:InvokeFunction\",\"Resource\":[\"arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:dbops-health-tools\",\"arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:dbops-query-tools\"]}]}"
echo "  ✅ lambda:InvokeFunction granted to $ROLE_NAME (gateway IAM role)"
# IAM trust/policy changes are eventually consistent; give them a moment to
# propagate so CreateFunction doesn't fail with "cannot be assumed by Lambda".
echo "  ⏳ Waiting 10s for IAM propagation..."
sleep 10
echo ""

# Deploy Lambda functions
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🚀 Deploying Lambda functions                                │"
echo "└──────────────────────────────────────────────────────────────┘"
SUBNET2="${SUBNET2:-$SUBNET1}"

for FUNC in health query; do
    FUNC_NAME="dbops-${FUNC}-tools"
    echo "  Deploying $FUNC_NAME..."

    # Create or update
    if aws lambda get-function --function-name $FUNC_NAME --region $AWS_REGION > /dev/null 2>&1; then
        # Function exists — it may still be settling from a prior run. Wait until
        # it's Active before updating, or update-function-code fails with
        # ResourceConflictException ("currently in the following state: Pending").
        aws lambda wait function-active --function-name $FUNC_NAME --region $AWS_REGION 2>/dev/null || true
        aws lambda update-function-code \
            --function-name $FUNC_NAME \
            --zip-file fileb://$SCRIPT_DIR/${FUNC}-tools.zip \
            --region $AWS_REGION --output text --query 'FunctionArn' > /dev/null
    else
        aws lambda create-function \
            --function-name $FUNC_NAME \
            --runtime python3.12 \
            --handler lambda_function.lambda_handler \
            --role $AGENTCORE_ROLE_ARN \
            --zip-file fileb://$SCRIPT_DIR/${FUNC}-tools.zip \
            --layers $LAYER_ARN \
            --timeout 60 \
            --memory-size 256 \
            --vpc-config SubnetIds=$SUBNET1,$SUBNET2,SecurityGroupIds=$SECURITY_GROUP_ID \
            --environment "Variables={DB_INSTANCE_ID=$DB_INSTANCE_ID,DB_SECRET_ID=$DB_SECRET_ID,AWS_REGION_NAME=$AWS_REGION,SNS_TOPIC_NAME=$SNS_TOPIC_NAME}" \
            --region $AWS_REGION --output text --query 'FunctionArn' > /dev/null
    fi

    # Wait until the function is fully Active (and any code update applied) before
    # adding permissions or registering it with the Gateway.
    aws lambda wait function-active --function-name $FUNC_NAME --region $AWS_REGION 2>/dev/null || true

    # Grant Gateway invoke permission
    aws lambda add-permission \
        --function-name $FUNC_NAME \
        --statement-id agentcore-gateway-invoke \
        --action lambda:InvokeFunction \
        --principal bedrock-agentcore.amazonaws.com \
        --region $AWS_REGION > /dev/null 2>&1 || true

    echo "  ✅ $FUNC_NAME deployed"
done
echo ""

# Create Gateway (Gateway + targets, AWS IAM auth)
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🌐 Creating AgentCore Gateway                                │"
echo "└──────────────────────────────────────────────────────────────┘"
python3 "$SCRIPT_DIR/setup_gateway.py"
echo ""

# Cleanup build artifacts
rm -f "$SCRIPT_DIR/health-tools.zip" "$SCRIPT_DIR/query-tools.zip"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🎉 AgentCore Gateway deployment complete!                    ║"
echo "╠══════════════════════════════════════════════════════════════╣"
GATEWAY_URL=$(python3 -c "import json; print(json.load(open('gateway_config.json'))['gateway_url'])")
echo "║  🌐 Gateway URL: $GATEWAY_URL"
echo "║  🔧 Total tools: 27                                          ║"
echo "║                                                              ║"
echo "║  Lambda Functions:                                           ║"
echo "║    📊 dbops-health-tools     (14 tools)                      ║"
echo "║    ⚡ dbops-query-tools      (13 tools)                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
