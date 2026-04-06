# SQL Server Agents

Each agent is a thin file that imports tools from `../tools/`, configuration from `../config/settings.py`, defines a system prompt, and creates the Strands `Agent` with an AgentCore entrypoint.

| Agent | File | Tools | Local Port |
|-------|------|-------|-----------|
| 📊 Database Health | `database_health_agent.py` | 14 | 9002 |
| ⚡ Query Performance | `query_performance_agent.py` | 13 | 9003 |
| 🔒 Security Audit | `security_audit_agent.py` | 8 | 9004 |
| 💾 Data Lifecycle | `data_lifecycle_agent.py` | 25 | 9005 |
| 🎯 Supervisor | `supervisor_agent.py` | 10 | 9006 |

## Agent Pattern

```python
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config.settings import AWS_REGION, LLM_MODEL, MEMORY_ID
from tools.database_health_tools import get_cpu_utilization, get_database_load, ...

app = BedrockAgentCoreApp()
model = BedrockModel(model_id=LLM_MODEL, region_name=AWS_REGION, temperature=0.3)

system_prompt = """You are the Database Health Agent..."""
_tools = [get_cpu_utilization, get_database_load, ...]
agent = Agent(system_prompt=system_prompt, model=model, tools=_tools)

@app.entrypoint
def database_health_agent(payload, context=None):
    # Builds session manager if MEMORY_ID is set, then invokes agent
    ...
```

## Memory Integration

When `MEMORY_ID` is set, each agent builds an `AgentCoreMemorySessionManager` at invocation time with:
- **Semantic strategy** — long-term fact extraction (top_k=5, relevance=0.3)
- **Summarization strategy** — session summaries (top_k=3, relevance=0.3)

All agents share one memory resource, enabling cross-agent knowledge recall.

When `MEMORY_ID` is empty, agents work normally without memory.
