import os
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.database_health_tools import (
    get_database_load, get_extended_database_load, get_wait_events, get_top_sql,
    get_users, get_applications, get_database_connections, get_cpu_utilization,
    get_free_storage, get_read_write_latency, get_iops, get_network_throughput,
    get_freeable_memory, send_email_notification
)

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are an RDS SQL Server performance specialist using Database Insights and CloudWatch metrics.

Available tools:

Database Insights (1-min granularity for ≤24h):
- get_database_load: Overall database load
- get_extended_database_load: Extended load with statistics (up to 7 days, but respects instance creation time)
- get_wait_events: Wait event breakdown (CPU, IO, Log, Other)
- get_top_sql: Top SQL queries with actual query text
- get_users: Database users and their load
- get_applications: Applications and their load

CloudWatch Metrics:
- get_database_connections: Connection counts
- get_cpu_utilization: CPU percentage
- get_free_storage: Disk space
- get_read_write_latency: Read/Write latency
- get_iops: Read/Write IOPS
- get_network_throughput: Network throughput
- get_freeable_memory: Available memory

Alerting:
- send_email_notification: Send performance alerts

**CRITICAL: When analyzing timelines:**
1. ALWAYS check 'instance_created' and 'actual_hours_available' from get_extended_database_load
2. NEVER assume data exists before instance creation time
3. State clearly when the instance was created vs when the issue started
4. If instance is young (< requested lookback), mention this explicitly

**Investigation workflow:**
1. For timeline questions: Use get_extended_database_load first to understand instance age and data availability
2. Identify bottleneck type with get_wait_events (CPU vs IO vs Lock)
3. Find problematic queries with get_top_sql
4. Check resource constraints with CloudWatch metrics
5. Correlate findings and provide specific recommendations
6. **ONLY send email alerts when explicitly requested in the user's prompt**"""

_tools = [
    get_database_load, get_extended_database_load, get_wait_events, get_top_sql,
    get_users, get_applications, get_database_connections, get_cpu_utilization,
    get_free_storage, get_read_write_latency, get_iops, get_network_throughput,
    get_freeable_memory, send_email_notification
]


def _build_session_manager(session_id):
    if not MEMORY_ID:
        return None
    try:
        from config.settings import MEMORY_ID as mid
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
        from bedrock_agentcore.memory import MemoryClient
        strategies = MemoryClient(region_name=AWS_REGION).get_memory_strategies(mid)
        strategy_map = {s['type']: s['strategyId'] for s in strategies}
        config = AgentCoreMemoryConfig(
            memory_id=mid, session_id=session_id, actor_id="dbops-agent",
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
def database_health_agent(payload, context=None):
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = _build_session_manager(session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=system_prompt, model=model, session_manager=sm, tools=_tools)
            return a(user_input).message['content'][0]['text']
    return agent(user_input).message['content'][0]['text']


if __name__ == "__main__":
    app.run(port=9002) if os.getenv("LOCAL_TESTING") else app.run()
