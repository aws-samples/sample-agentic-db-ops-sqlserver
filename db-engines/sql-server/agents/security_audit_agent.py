import os
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.security_audit_tools import (
    check_tde_status, check_backup_encryption, get_failed_login_attempts,
    get_rds_events, get_configuration_changes_from_cloudtrail,
    check_rds_security_settings, check_rds_audit_settings, send_email_notification
)

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are an RDS SQL Server security audit specialist focused on AWS-level security.

Available tools:

**Encryption & Data Protection:**
- check_tde_status: Transparent Data Encryption status per database (DMV)
- check_backup_encryption: RDS storage and snapshot encryption status (RDS API)

**Auditing & Compliance:**
- get_failed_login_attempts: Failed login attempts from CloudWatch Logs
- get_rds_events: RDS event history including configuration changes (RDS API)
- get_configuration_changes_from_cloudtrail: Detailed configuration changes with who/what/when (CloudTrail)
- check_rds_audit_settings: SQL Server Audit (DAS) and backup/restore settings (RDS API)

**RDS Security Configuration:**
- check_rds_security_settings: Public accessibility, VPC, IAM auth, deletion protection (RDS API)

**Alerting:**
- send_email_notification: Send security alerts via SNS

**Investigation workflow:**
1. Encryption Audit: check_tde_status + check_backup_encryption
2. Compliance Audit: check_rds_audit_settings, get_failed_login_attempts, get_rds_events, get_configuration_changes_from_cloudtrail
3. Infrastructure Security: check_rds_security_settings
4. **ONLY send email alerts when explicitly requested in the user's prompt**"""

_tools = [
    check_tde_status, check_backup_encryption, get_failed_login_attempts,
    get_rds_events, get_configuration_changes_from_cloudtrail,
    check_rds_audit_settings, check_rds_security_settings, send_email_notification
]


def _build_session_manager(session_id):
    if not MEMORY_ID:
        return None
    try:
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
        from bedrock_agentcore.memory import MemoryClient
        strategies = MemoryClient(region_name=AWS_REGION).get_memory_strategies(MEMORY_ID)
        strategy_map = {s['type']: s['strategyId'] for s in strategies}
        config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID, session_id=session_id, actor_id="dbops-agent",
            retrieval_config={
                "/strategies/{memoryStrategyId}/actors/{actorId}/": RetrievalConfig(top_k=5, relevance_score=0.3, strategy_id=strategy_map.get('SEMANTIC', '')),
                "/strategies/{memoryStrategyId}/actors/{actorId}/sessions/{sessionId}/": RetrievalConfig(top_k=3, relevance_score=0.3, strategy_id=strategy_map.get('SUMMARIZATION', '')),
            },
        )
        return AgentCoreMemorySessionManager(agentcore_memory_config=config, region_name=AWS_REGION)
    except Exception as e:
        print(f"[WARN] Memory init failed, running without memory: {e}")
        return None


agent = Agent(system_prompt=system_prompt, model=model, tools=_tools)


@app.entrypoint
def security_audit_agent(payload, context=None):
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = _build_session_manager(session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=system_prompt, model=model, session_manager=sm, tools=_tools)
            return a(user_input).message['content'][0]['text']
    return agent(user_input).message['content'][0]['text']


if __name__ == "__main__":
    app.run(port=9004) if os.getenv("LOCAL_TESTING") else app.run()
