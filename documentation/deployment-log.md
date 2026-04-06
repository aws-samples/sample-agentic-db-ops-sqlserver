# Deployment Log — agentic-db-ops

> **Note:** This log captures the initial deployment and debugging process. Some values (ARNs, subnet IDs, secret ARNs) are from earlier deployments and may not match the current `.env`. Always refer to `.env` for current values.

**Region**: us-east-1  
**Account**: 857198250696  
**Date Started**: 2025-07-15  

---

## Phase 0: Infrastructure Deployment (Pre-Test Plan)

### 0.1 — Deploy foundational infrastructure

```bash
aws cloudformation deploy \
  --template-file templates/infrastructure.yaml \
  --stack-name dbops-infra \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Stack**: `dbops-infra` — CREATE_COMPLETE  
**Key Outputs**:

| Output | Value |
|--------|-------|
| DB_INSTANCE_ID | `dbops-infra-sqlserver` |
| DB_SECRET_ID | `arn:aws:secretsmanager:us-east-1:857198250696:secret:dbops-infra-sqlserver-secret-cOLtZL` |
| SECURITY_GROUP_ID | `sg-0357fe58bb40abf42` |
| SUBNET1 | `subnet-013f0eccab9019aba` |
| SUBNET2 | `subnet-0a1c406e0d801bf5b` |
| SNS_TOPIC_NAME | `dbops-infra-alerts` |
| RDS Endpoint | `dbops-infra-sqlserver.cxmadmqispyg.us-east-1.rds.amazonaws.com:1433` |
| Bastion IP | `54.242.188.155` |
| VPC | `vpc-0a81363e9ba93cf58` |

**Notes**:
- SQL Server edition changed from Enterprise (`sqlserver-ee`) to Standard (`sqlserver-se`) per cost preference.
- First deploy failed due to non-ASCII em dash characters (`—`) in security group descriptions. Fixed by replacing with regular dashes (`-`).

---

## Phase 1: Prerequisites ✅

### 1.1 — Create virtual environment

```bash
cd /Users/vsriv/Documents/agentic-db-ops
python3 -m venv .venv
source .venv/bin/activate
```

**Python version**: 3.12.7

### 1.2 — Install dependencies

```bash
pip install -r db-engines/sql-server/requirements.txt
```

**Key packages installed**:
- strands-agents 1.30.0
- bedrock-agentcore 1.4.6
- pymssql 2.3.13
- boto3 1.42.69

### 1.3 — Verify agentcore CLI

```bash
agentcore --help
```

Confirmed working. Commands available: `create`, `dev`, `deploy`, `invoke`, etc.

### 1.4 — Verify Bedrock model access

Confirmed Claude Sonnet is enabled in Bedrock console for us-east-1.

---

## Phase 2: Deploy AgentCore IAM Role ✅

### 2.1 — Clean up pre-existing role

The role `AgentCoreDBOpsRole` already existed from a prior manual creation, causing CloudFormation to fail with: *"The policy AgentCoreDBOpsPolicy already exists on the role AgentCoreDBOpsRole."*

```bash
aws cloudformation delete-stack --stack-name dbops-agentcore-role --region us-east-1
aws iam delete-role-policy --role-name AgentCoreDBOpsRole --policy-name AgentCoreDBOpsPolicy
aws iam detach-role-policy --role-name AgentCoreDBOpsRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
aws iam detach-role-policy --role-name AgentCoreDBOpsRole --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam detach-role-policy --role-name AgentCoreDBOpsRole --policy-arn arn:aws:iam::aws:policy/BedrockAgentCoreFullAccess
aws iam delete-role --role-name AgentCoreDBOpsRole
```

### 2.2 — Deploy agentcore-role.yaml

```bash
aws cloudformation deploy \
  --template-file templates/agentcore-role.yaml \
  --stack-name dbops-agentcore-role \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Stack**: `dbops-agentcore-role` — CREATE_COMPLETE  
**Outputs**:

| Output | Value |
|--------|-------|
| RoleName | `AgentCoreDBOpsRole` |
| RoleArn | `arn:aws:iam::857198250696:role/AgentCoreDBOpsRole` |

**Lesson learned**: Check for pre-existing IAM roles before deploying. If a role exists outside CloudFormation, delete it first (detach all policies, remove inline policies, then delete the role).

---

## Phase 3: Set Environment Variables ✅

### 3.1 — Export environment variables

```bash
source .venv/bin/activate
export DB_INSTANCE_ID=dbops-infra-sqlserver
export DB_SECRET_ID=arn:aws:secretsmanager:us-east-1:857198250696:secret:dbops-infra-sqlserver-secret-cOLtZL
export AWS_REGION=us-east-1
export SNS_TOPIC_NAME=dbops-infra-alerts
export SECURITY_GROUP_ID=sg-0357fe58bb40abf42
export SUBNET1=subnet-013f0eccab9019aba
export SUBNET2=subnet-0a1c406e0d801bf5b
export AGENTCORE_ROLE_ARN=arn:aws:iam::857198250696:role/AgentCoreDBOpsRole
```

### 3.2 — Created `.env` file

Created `.env` at project root for easy re-sourcing: `source .env`

**Deferred vars** (set during Phase 4):
- `MEMORY_ID` — created by `deploy.sh`
- `HEALTH_AGENT_ARN`, `PERFORMANCE_AGENT_ARN`, `SECURITY_AGENT_ARN`, `LIFECYCLE_AGENT_ARN` — set after sub-agent deployment

**Note**: Each `executeBash` call runs in a new shell, so env vars must be re-sourced. The `.env` file makes this easy: `source .venv/bin/activate && source .env`

---

## Phase 4: Deploy Agents ✅

### 4.1 — deploy.sh fixes required

Three issues discovered and fixed in `deploy.sh`:

1. **Unsupported AZ**: SUBNET2 (`subnet-0a1c406e0d801bf5b`) is in `us-east-1b` (`use1-az6`), which AgentCore doesn't support (Fargate limitation). Supported AZs: `use1-az1`, `use1-az2`, `use1-az4`. **Fix**: Set SUBNET2 = SUBNET1 (single subnet mode).
2. **Memory ID parsing**: CLI `agentcore memory list` uses rich table formatting that truncates IDs. `awk '{print $4}'` grabbed `ACTIVE` instead of the ID. **Fix**: Use Python SDK (`bedrock_agentcore.memory.MemoryClient`) to extract full memory ID.
3. **Agent conflict on re-deploy**: Partially created agents from failed runs cause `ConflictException`. **Fix**: Added `--auto-update-on-conflict` flag to all `agentcore deploy` commands.
4. **Subnet deduplication**: Passing same subnet twice (`$SUBNET1,$SUBNET1`) caused "subnets could not be found" error. **Fix**: Deduplicate when SUBNET1 == SUBNET2.
5. **ARN extraction failure**: `agentcore status --verbose` requires local `.bedrock_agentcore.yaml` config, but the temp staging dir is cleaned up between steps. Supervisor deployed manually with known ARNs.

Also fixed `cleanup.sh`: `--yes` → `--force` (correct flag per CLI).

### 4.2 — Shared memory created

```
Memory ID: dbops_shared_memory-4G8tW791gO (initial), later recreated as dbops_shared_memory-7VsooA5duY
Status: ACTIVE
Strategies: semanticMemoryStrategy (dbops_semantic) + summaryMemoryStrategy (dbops_summarization)
Retention: 365 days (max allowed)
Namespaces: dbops (semantic), dbops/{sessionId} (summarization)
```

### 4.3 — All 5 agents deployed

| Agent | ARN | Status |
|-------|-----|--------|
| 📊 Database Health | `arn:aws:bedrock-agentcore:us-east-1:857198250696:runtime/database_health_agent-9Ci7YP85Zu` | ✅ Deployed |
| ⚡ Query Performance | `arn:aws:bedrock-agentcore:us-east-1:857198250696:runtime/query_performance_agent-ZCB35gBAW6` | ✅ Deployed |
| 🔒 Security Audit | `arn:aws:bedrock-agentcore:us-east-1:857198250696:runtime/security_audit_agent-QdGueA9WCE` | ✅ Deployed |
| 💾 Data Lifecycle | `arn:aws:bedrock-agentcore:us-east-1:857198250696:runtime/data_lifecycle_agent-avH7i25Cq2` | ✅ Deployed |
| 🎯 Supervisor | `arn:aws:bedrock-agentcore:us-east-1:857198250696:runtime/supervisor_agent-F14wHt6L7I` | ✅ Deployed |

**Deployment details**: Direct code deploy, Python 3.12, ARM64, VPC mode (single subnet `us-east-1a`), S3 bucket `bedrock-agentcore-codebuild-sources-857198250696-us-east-1`.

### 4.4 — Updated `.env` with all ARNs

All deferred variables now populated in `.env`.

---

## Phase 5–9: Agent Testing

All 5 agents were tested end-to-end via `./invoke.sh`. Key issues found and fixed during testing:

- **Agents returned empty responses** — Root cause: agents deployed to public subnet while VPC endpoints were in private subnets. Fixed by redeploying to private subnet.
- **DB connection failures** — `get_db_connection()` in query_performance, security_audit, and data_lifecycle tools was not resolving host/port. Fixed to use RDS `describe_db_instances` API with `DB_INSTANCE_ID`.
- **Invoke script response handling** — Rewrote `scripts/invoke_agent.py` to handle AgentCore's streaming response format.
- **Supervisor stale ARNs** — Sub-agent ARNs change on each deploy. Fixed `deploy.sh` to dynamically resolve ARNs via boto3 before deploying supervisor.
- **Memory strategy naming** — API requires `[a-zA-Z][a-zA-Z0-9_]` pattern (no hyphens). Used underscores in all names.
- **Summarization namespace** — Requires `{sessionId}` placeholder. Used `dbops/{sessionId}`.

All agents confirmed working with shared memory.

---

## Cleanup

Cleanup tested via `python3 scripts/cleanup_agents.py`. Uses `delete_agent_runtime` boto3 API (not `agentcore destroy` which deletes the IAM role). Also deletes shared memory. ENI notice displayed about 8-hour persistence.
