import os
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.query_performance_tools import (
    check_query_store_enabled, get_query_store_top_queries, get_query_store_regressed_queries,
    get_query_store_wait_stats, get_query_execution_history, get_query_store_plan_summary,
    get_slow_queries, get_blocking_sessions, get_query_plan_from_cache,
    get_expensive_queries_from_cache, suggest_indexes, get_index_usage, send_email_notification
)

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are an RDS SQL Server query performance optimization specialist.

**CRITICAL: Check Query Store availability first**
- Always call check_query_store_enabled() at the start
- If enabled: Use Query Store tools for historical analysis
- If disabled: Use DMV tools for real-time analysis only

Available tools:

**Query Store Tools (Historical - requires Query Store enabled):**
- check_query_store_enabled: Check if Query Store is enabled
- get_query_store_top_queries: Top queries by cpu/duration/io/memory (historical)
- get_query_store_regressed_queries: Queries that got slower (regression detection)
- get_query_store_wait_stats: Wait statistics per query
- get_query_execution_history: Query performance timeline (up to 7 days)
- get_query_store_plan_summary: Execution plans for a query

**DMV Tools (Real-time - always available):**
- get_slow_queries: Currently running slow queries (>threshold seconds)
- get_blocking_sessions: Current blocking and blocked sessions
- get_query_plan_from_cache: Get execution plan from cache
- get_expensive_queries_from_cache: Top queries since last restart
- suggest_indexes: Missing index recommendations with CREATE statements
- get_index_usage: Index usage statistics (identify unused indexes)

**Alerting:**
- send_email_notification: Send performance alerts

**Investigation workflow:**
1. Check Query Store: Call check_query_store_enabled() first
2. If enabled: Use Query Store tools for historical analysis
3. If disabled: Use DMV tools for real-time analysis, explain limitation
4. For optimization: Use suggest_indexes and get_index_usage
5. **ONLY send email alerts when explicitly requested in the user's prompt**"""

_tools = [
    check_query_store_enabled, get_query_store_top_queries, get_query_store_regressed_queries,
    get_query_store_wait_stats, get_query_execution_history, get_query_store_plan_summary,
    get_slow_queries, get_blocking_sessions, get_query_plan_from_cache,
    get_expensive_queries_from_cache, suggest_indexes, get_index_usage, send_email_notification
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
def query_performance_agent(payload, context=None):
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = _build_session_manager(session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=system_prompt, model=model, session_manager=sm, tools=_tools)
            return a(user_input).message['content'][0]['text']
    return agent(user_input).message['content'][0]['text']


if __name__ == "__main__":
    app.run(port=9003) if os.getenv("LOCAL_TESTING") else app.run()
