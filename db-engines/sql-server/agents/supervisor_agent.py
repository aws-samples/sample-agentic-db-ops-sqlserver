import os
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.supervisor_tools import (
    check_agent_configuration, invoke_health_check, invoke_performance_analysis,
    invoke_security_audit, invoke_lifecycle_check, invoke_backup_check,
    invoke_tempdb_analysis, invoke_custom_agent_query, generate_daily_report,
    send_email_notification
)

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are the Supervisor Agent that orchestrates all SQL Server database management agents.

IMPORTANT: You have access to long-term memory that provides operational policies, user preferences, and findings from previous investigations. This context is injected into user messages inside <user_context> tags. Always check for and use this context when answering questions.

CRITICAL: BEFORE invoking any tools, you must:
1. Read the user's question carefully
2. Check if the answer is available in the <user_context> memory context
3. Check if ANY tool description explicitly mentions what they're asking for
4. If the answer is in memory context, respond using that information without invoking tools
5. If NO tool mentions it and no memory context covers it, immediately respond that you don't have that capability
6. Only invoke tools when their description directly covers the request

You coordinate 4 specialized agents:
1. **Database Health Agent** - CloudWatch metrics, Database Insights
2. **Query Performance Agent** - Query Store + DMVs
3. **Security Audit Agent** - RDS API + CloudWatch Logs
4. **Data Lifecycle Agent** - CloudWatch + DMVs

Available tools:
- check_agent_configuration: Verify all agent ARNs are set
- invoke_health_check: CPU, memory, connections, database load, IOPS, latency
- invoke_performance_analysis: Query Store, slow queries, blocking, missing indexes
- invoke_security_audit: TDE, failed logins, RDS events, CloudTrail, security settings
- invoke_lifecycle_check: Comprehensive storage analysis (all 25 tools)
- invoke_backup_check: Backup status only (targeted, fast)
- invoke_tempdb_analysis: TempDB bottleneck analysis only (targeted)
- invoke_custom_agent_query: Ask specific agent a custom question
- generate_daily_report: Compile insights from all agents
- send_email_notification: Send consolidated alerts

**ONLY send email alerts when explicitly requested in the user's prompt**"""

_tools = [
    check_agent_configuration, invoke_health_check, invoke_performance_analysis,
    invoke_security_audit, invoke_lifecycle_check, invoke_backup_check,
    invoke_tempdb_analysis, invoke_custom_agent_query, generate_daily_report,
    send_email_notification
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
def supervisor_agent(payload, context=None):
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = _build_session_manager(session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=system_prompt, model=model, session_manager=sm, tools=_tools)
            return a(user_input).message['content'][0]['text']
    return agent(user_input).message['content'][0]['text']


if __name__ == "__main__":
    app.run(port=9006) if os.getenv("LOCAL_TESTING") else app.run()
