import os
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.data_lifecycle_tools import (
    get_storage_metrics, get_iops_trends, get_throughput_trends, get_latency_trends,
    get_queue_depth_trends, analyze_storage_growth, get_storage_configuration,
    recommend_storage_upgrade, get_database_size, get_table_sizes, get_index_sizes,
    identify_old_data, get_fragmentation_status, get_tempdb_size,
    get_tempdb_space_usage_by_session, get_tempdb_space_usage_by_query,
    get_tempdb_contention, get_tempdb_io_stats, check_tempdb_file_configuration,
    get_temp_table_usage, get_version_store_usage, validate_tempdb_configuration,
    analyze_tempdb_bottleneck, check_backup_status, send_email_notification
)

app = BedrockAgentCoreApp()

model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are an RDS SQL Server data lifecycle management specialist.

Available tools:

**CloudWatch Storage Metrics (with timeline analysis):**
- get_storage_metrics: Storage usage and growth trends
- get_iops_trends: IOPS trends
- get_throughput_trends: Read/write throughput trends
- get_latency_trends: Read/write latency trends
- get_queue_depth_trends: Disk queue depth (bottleneck indicator)
- analyze_storage_growth: Storage growth rate and days until full

**Storage Configuration & Recommendations:**
- get_storage_configuration: Current storage type (gp2/gp3/io1/io2), IOPS, throughput
- recommend_storage_upgrade: Analyze metrics and suggest gp3/io2 upgrades

**DMV Storage Analysis:**
- get_database_size: Total database sizes
- get_table_sizes: Top 20 tables by space
- get_index_sizes: Top 20 indexes by space
- identify_old_data: Find archival candidates by date
- get_fragmentation_status: Index fragmentation >10%

**TempDB Critical Analysis:**
- get_tempdb_size: Current size, used/free space per file
- get_tempdb_space_usage_by_session: Which sessions consuming TempDB
- get_tempdb_space_usage_by_query: Which queries using TempDB
- get_tempdb_contention: PFS/SGAM/GAM page latch contention
- get_tempdb_io_stats: TempDB file I/O latency and stalls
- check_tempdb_file_configuration: File count, sizes, growth settings
- get_temp_table_usage: Active temp tables (#temp, ##global)
- get_version_store_usage: Version store size (row versioning)
- validate_tempdb_configuration: Best practices check
- analyze_tempdb_bottleneck: Comprehensive root cause analysis

**Backup & Compliance:**
- check_backup_status: Backup retention, recent snapshots

**Alerting:**
- send_email_notification: Send lifecycle alerts

**Investigation workflow:**
1. Storage Analysis: get_storage_metrics + analyze_storage_growth
2. Performance Bottlenecks: get_latency_trends, get_queue_depth_trends, get_iops_trends
3. Storage Optimization: recommend_storage_upgrade
4. Space Management: get_table_sizes, get_index_sizes
5. TempDB Issues: analyze_tempdb_bottleneck
6. Data Archival: identify_old_data
7. Maintenance: get_fragmentation_status
8. Compliance: check_backup_status
9. **ONLY send email alerts when explicitly requested in the user's prompt**"""

_tools = [
    get_storage_metrics, get_iops_trends, get_throughput_trends, get_latency_trends,
    get_queue_depth_trends, analyze_storage_growth, get_storage_configuration,
    recommend_storage_upgrade, get_database_size, get_table_sizes, get_index_sizes,
    identify_old_data, get_fragmentation_status, get_tempdb_size,
    get_tempdb_space_usage_by_session, get_tempdb_space_usage_by_query,
    get_tempdb_contention, get_tempdb_io_stats, check_tempdb_file_configuration,
    get_temp_table_usage, get_version_store_usage, validate_tempdb_configuration,
    analyze_tempdb_bottleneck, check_backup_status, send_email_notification
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
def data_lifecycle_agent(payload, context=None):
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = _build_session_manager(session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=system_prompt, model=model, session_manager=sm, tools=_tools)
            return a(user_input).message['content'][0]['text']
    return agent(user_input).message['content'][0]['text']


if __name__ == "__main__":
    app.run(port=9005) if os.getenv("LOCAL_TESTING") else app.run()
