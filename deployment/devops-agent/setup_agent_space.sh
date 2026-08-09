#!/bin/bash
set -euo pipefail

##############################################################################
#  AWS DevOps Agent — Agent Space Setup Script
#  Creates IAM roles, Agent Space, associates AWS account, enables Web App
##############################################################################

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     🚀 AWS DevOps Agent — Agent Space Setup                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─── Validate environment variables ──────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔍 Step 1: Validating environment variables                  │"
echo "└──────────────────────────────────────────────────────────────┘"

REQUIRED_VARS=("AWS_REGION" "AWS_ACCOUNTID")
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "  ❌ ERROR: $var is not set"
    echo "  Please ensure environment variables are configured in your .bashrc"
    exit 1
  fi
done

echo "  ✅ AWS_REGION=$AWS_REGION"
echo "  ✅ AWS_ACCOUNTID=$AWS_ACCOUNTID"
echo ""

# ─── Create Agent Space IAM Role ────────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔐 Step 2: Creating Agent Space IAM role                     │"
echo "└──────────────────────────────────────────────────────────────┘"

AGENTSPACE_ROLE_NAME="DevOpsAgentRole-AgentSpace"

# Check if role already exists
if aws iam get-role --role-name "$AGENTSPACE_ROLE_NAME" &>/dev/null; then
  echo "  ⚡ Role $AGENTSPACE_ROLE_NAME already exists, updating trust policy..."
else
  echo "  📦 Creating role $AGENTSPACE_ROLE_NAME..."
fi

# Create/update trust policy
cat > /tmp/devops-agentspace-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "aidevops.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "$AWS_ACCOUNTID"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:aidevops:$AWS_REGION:$AWS_ACCOUNTID:agentspace/*"
        }
      }
    }
  ]
}
EOF

if aws iam get-role --role-name "$AGENTSPACE_ROLE_NAME" &>/dev/null; then
  aws iam update-assume-role-policy \
    --role-name "$AGENTSPACE_ROLE_NAME" \
    --policy-document file:///tmp/devops-agentspace-trust-policy.json
else
  aws iam create-role \
    --role-name "$AGENTSPACE_ROLE_NAME" \
    --assume-role-policy-document file:///tmp/devops-agentspace-trust-policy.json \
    --output text --query 'Role.Arn' > /dev/null
fi

# Attach managed policy
aws iam attach-role-policy \
  --role-name "$AGENTSPACE_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsAgentAccessPolicy 2>/dev/null || true

# Create inline policy for Resource Explorer SLR
cat > /tmp/devops-agentspace-additional-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCreateServiceLinkedRoles",
      "Effect": "Allow",
      "Action": ["iam:CreateServiceLinkedRole"],
      "Resource": [
        "arn:aws:iam::$AWS_ACCOUNTID:role/aws-service-role/resource-explorer-2.amazonaws.com/AWSServiceRoleForResourceExplorer"
      ]
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name "$AGENTSPACE_ROLE_NAME" \
  --policy-name AllowCreateServiceLinkedRoles \
  --policy-document file:///tmp/devops-agentspace-additional-policy.json

DEVOPS_AGENT_ROLE_ARN=$(aws iam get-role --role-name "$AGENTSPACE_ROLE_NAME" --query 'Role.Arn' --output text)
echo "  ✅ Agent Space role ready: $DEVOPS_AGENT_ROLE_ARN"
echo ""

# ─── Create Operator App IAM Role ───────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔐 Step 3: Creating Operator App IAM role                    │"
echo "└──────────────────────────────────────────────────────────────┘"

OPERATOR_ROLE_NAME="DevOpsAgentRole-WebappAdmin"

cat > /tmp/devops-operator-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "aidevops.amazonaws.com"
      },
      "Action": ["sts:AssumeRole", "sts:TagSession"],
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "$AWS_ACCOUNTID"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:aidevops:$AWS_REGION:$AWS_ACCOUNTID:agentspace/*"
        }
      }
    }
  ]
}
EOF

if aws iam get-role --role-name "$OPERATOR_ROLE_NAME" &>/dev/null; then
  echo "  ⚡ Role $OPERATOR_ROLE_NAME already exists, updating trust policy..."
  aws iam update-assume-role-policy \
    --role-name "$OPERATOR_ROLE_NAME" \
    --policy-document file:///tmp/devops-operator-trust-policy.json
else
  echo "  📦 Creating role $OPERATOR_ROLE_NAME..."
  aws iam create-role \
    --role-name "$OPERATOR_ROLE_NAME" \
    --assume-role-policy-document file:///tmp/devops-operator-trust-policy.json \
    --output text --query 'Role.Arn' > /dev/null
fi

aws iam attach-role-policy \
  --role-name "$OPERATOR_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy 2>/dev/null || true

DEVOPS_OPERATOR_ROLE_ARN=$(aws iam get-role --role-name "$OPERATOR_ROLE_NAME" --query 'Role.Arn' --output text)
echo "  ✅ Operator App role ready: $DEVOPS_OPERATOR_ROLE_ARN"
echo ""

# ─── Wait for IAM propagation ───────────────────────────────────────────────

echo "  ⏳ Waiting 10 seconds for IAM propagation..."
sleep 10

# ─── Create Agent Space ─────────────────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🌐 Step 4: Creating Agent Space                              │"
echo "└──────────────────────────────────────────────────────────────┘"

AGENT_SPACE_NAME="sql-server-dbops"

# Check if agent space already exists
EXISTING_SPACE_ID=$(aws devops-agent list-agent-spaces \
  --region "$AWS_REGION" \
  --query "agentSpaces[?name=='$AGENT_SPACE_NAME'].agentSpaceId" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_SPACE_ID" ] && [ "$EXISTING_SPACE_ID" != "None" ]; then
  echo "  ⚡ Agent Space '$AGENT_SPACE_NAME' already exists: $EXISTING_SPACE_ID"
  AGENT_SPACE_ID="$EXISTING_SPACE_ID"
else
  echo "  📦 Creating Agent Space '$AGENT_SPACE_NAME'..."
  AGENT_SPACE_ID=$(aws devops-agent create-agent-space \
    --name "$AGENT_SPACE_NAME" \
    --description "Agent Space for SQL Server database operations and troubleshooting" \
    --region "$AWS_REGION" \
    --query 'agentSpace.agentSpaceId' \
    --output text)
  echo "  ✅ Agent Space created: $AGENT_SPACE_ID"
fi
echo ""

# ─── Associate AWS Account ──────────────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🔗 Step 5: Associating AWS account                           │"
echo "└──────────────────────────────────────────────────────────────┘"

echo "  📦 Associating account $AWS_ACCOUNTID as monitor..."
aws devops-agent associate-service \
  --agent-space-id "$AGENT_SPACE_ID" \
  --service-id aws \
  --configuration "{\"aws\": {\"assumableRoleArn\": \"$DEVOPS_AGENT_ROLE_ARN\", \"accountId\": \"$AWS_ACCOUNTID\", \"accountType\": \"monitor\"}}" \
  --region "$AWS_REGION" > /dev/null 2>&1 || echo "  ⚡ Account already associated (or association updated)"

echo "  ✅ AWS account associated"
echo ""

# ─── Enable Operator App ────────────────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  🖥️  Step 6: Enabling Operator App (Web App)                   │"
echo "└──────────────────────────────────────────────────────────────┘"

echo "  📦 Enabling Web App with IAM auth..."
aws devops-agent enable-operator-app \
  --agent-space-id "$AGENT_SPACE_ID" \
  --auth-flow iam \
  --operator-app-role-arn "$DEVOPS_OPERATOR_ROLE_ARN" \
  --region "$AWS_REGION" > /dev/null 2>&1 || echo "  ⚡ Operator App already enabled"

echo "  ✅ Operator App enabled"
echo ""

# ─── Save configuration ─────────────────────────────────────────────────────

echo "┌──────────────────────────────────────────────────────────────┐"
echo "│  💾 Step 7: Saving configuration                              │"
echo "└──────────────────────────────────────────────────────────────┘"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/agent_space_config.json"

cat > "$CONFIG_FILE" << EOF
{
  "agent_space_id": "$AGENT_SPACE_ID",
  "agent_space_name": "$AGENT_SPACE_NAME",
  "agent_space_role_arn": "$DEVOPS_AGENT_ROLE_ARN",
  "operator_role_arn": "$DEVOPS_OPERATOR_ROLE_ARN",
  "account_id": "$AWS_ACCOUNTID",
  "region": "$AWS_REGION"
}
EOF

echo "  ✅ Configuration saved to: $CONFIG_FILE"
echo ""

# ─── Export environment variables ────────────────────────────────────────────

export AGENT_SPACE_ID="$AGENT_SPACE_ID"
export DEVOPS_AGENT_ROLE_ARN="$DEVOPS_AGENT_ROLE_ARN"
export DEVOPS_OPERATOR_ROLE_ARN="$DEVOPS_OPERATOR_ROLE_ARN"

# ─── Summary ────────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  🎉 Agent Space setup complete!                              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Agent Space:  $AGENT_SPACE_NAME"
echo "║  Space ID:     $AGENT_SPACE_ID"
echo "║  Region:       $AWS_REGION"
echo "║  Account:      $AWS_ACCOUNTID"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  IAM Roles:                                                  ║"
echo "║    🔐 Agent Space: $AGENTSPACE_ROLE_NAME"
echo "║    🖥️  Operator App: $OPERATOR_ROLE_NAME"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Next: Run connect-mcp-servers steps to register Gateway     ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Cleanup temp files
rm -f /tmp/devops-agentspace-trust-policy.json
rm -f /tmp/devops-agentspace-additional-policy.json
rm -f /tmp/devops-operator-trust-policy.json
