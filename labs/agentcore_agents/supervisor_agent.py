# Updated: 2026-03-15
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import boto3
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any

app = BedrockAgentCoreApp()

# AgentCore Memory — cross-session knowledge retention
MEMORY_ID = os.getenv('MEMORY_ID')

def build_session_manager(session_id="default", actor_id="dbops-agent"):
    from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
    from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
    from bedrock_agentcore.memory import MemoryClient
    if not MEMORY_ID:
        return None
    strategies = MemoryClient(region_name=os.getenv('AWS_REGION', 'us-west-2')).get_memory_strategies(MEMORY_ID)
    strategy_map = {s['type']: s['strategyId'] for s in strategies}
    semantic_id = strategy_map.get('SEMANTIC', '')
    summary_id = strategy_map.get('SUMMARIZATION', '')
    config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=session_id,
        actor_id=actor_id,
        retrieval_config={
            "/strategies/{memoryStrategyId}/actors/{actorId}/": RetrievalConfig(top_k=5, relevance_score=0.3, strategy_id=semantic_id),
            "/strategies/{memoryStrategyId}/actors/{actorId}/sessions/{sessionId}/": RetrievalConfig(top_k=3, relevance_score=0.3, strategy_id=summary_id),
        },
    )
    return AgentCoreMemorySessionManager(
        agentcore_memory_config=config,
        region_name=os.getenv('AWS_REGION', 'us-west-2'),
    )

# Configuration from environment variables
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')

# Agent ARNs from environment (set during deployment)
HEALTH_AGENT_ARN = os.getenv('HEALTH_AGENT_ARN', '')
PERFORMANCE_AGENT_ARN = os.getenv('PERFORMANCE_AGENT_ARN', '')
SECURITY_AGENT_ARN = os.getenv('SECURITY_AGENT_ARN', '')
LIFECYCLE_AGENT_ARN = os.getenv('LIFECYCLE_AGENT_ARN', '')

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.3
)

# Helper function to invoke other agents via AgentCore Runtime
def invoke_agent_runtime(agent_arn: str, prompt: str) -> Dict[str, Any]:
    """Invoke AgentCore Runtime agent"""
    try:
        if not agent_arn:
            return {'error': 'Agent ARN not configured'}
        
        agent_core_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)
        
        payload = json.dumps({"prompt": prompt}).encode()
        
        response = agent_core_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            payload=payload
        )
        
        # Handle streaming response
        if "text/event-stream" in response.get("contentType", ""):
            content = []
            for line in response["response"].iter_lines(chunk_size=10):
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        line = line[6:]
                        content.append(line)
            return {'response': "\n".join(content)}
        
        # Handle JSON response
        elif response.get("contentType") == "application/json":
            content = []
            for chunk in response.get("response", []):
                content.append(chunk.decode('utf-8'))
            return {'response': json.loads(''.join(content))}
        
        return {'response': str(response)}
    except Exception as e:
        return {'error': str(e)}

# ===== DEBUG TOOL =====

@tool
def check_agent_configuration() -> Dict[str, Any]:
    """Check if agent ARNs are configured"""
    return {
        'health_agent_arn': HEALTH_AGENT_ARN or 'NOT SET',
        'performance_agent_arn': PERFORMANCE_AGENT_ARN or 'NOT SET',
        'security_agent_arn': SECURITY_AGENT_ARN or 'NOT SET',
        'lifecycle_agent_arn': LIFECYCLE_AGENT_ARN or 'NOT SET'
    }

# ===== AGENT INVOCATION TOOLS =====

@tool
def invoke_health_check() -> Dict[str, Any]:
    """Invoke Database Health Agent for comprehensive health check"""
    prompt = """Provide a comprehensive health check including:
    - Current CPU utilization
    - Memory usage
    - Database connections
    - Database load
    - Storage space
    - IOPS and latency
    
    Identify any critical issues."""
    
    return invoke_agent_runtime(HEALTH_AGENT_ARN, prompt)

@tool
def invoke_performance_analysis() -> Dict[str, Any]:
    """Invoke Query Performance Agent for performance analysis"""
    prompt = """Analyze query performance including:
    - Top CPU-consuming queries
    - Wait statistics
    - Slow running queries
    - Blocking sessions
    - Missing index recommendations
    
    Identify performance bottlenecks."""
    
    return invoke_agent_runtime(PERFORMANCE_AGENT_ARN, prompt)

@tool
def invoke_security_audit() -> Dict[str, Any]:
    """Invoke Security Audit Agent for security review"""
    prompt = """Perform security audit including:
    - TDE encryption status
    - Backup encryption
    - Failed login attempts (last 7 days)
    - RDS events and configuration changes
    - CloudTrail activity
    - RDS security settings
    
    Identify security concerns and suspicious activities."""
    
    return invoke_agent_runtime(SECURITY_AGENT_ARN, prompt)

@tool
def invoke_lifecycle_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent for comprehensive storage and lifecycle review"""
    prompt = """Review data lifecycle including:
    - Storage usage and growth trends
    - IOPS, throughput, and latency trends
    - Storage type and upgrade recommendations
    - TempDB analysis and bottlenecks
    - Largest tables and indexes
    - Backup status
    - Fragmentation status
    
    Identify storage optimization opportunities."""
    
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN, prompt)

@tool
def invoke_backup_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for backup status"""
    prompt = """Check backup status only:
    - Use check_backup_status tool
    - Backup retention period
    - Recent snapshots
    - Latest restorable time
    
    Report backup compliance."""
    
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN, prompt)

@tool
def invoke_tempdb_analysis() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for TempDB analysis"""
    prompt = """Analyze TempDB only:
    - Use analyze_tempdb_bottleneck tool
    - TempDB size and usage
    - Configuration issues
    - Contention and I/O problems
    
    Report TempDB bottlenecks."""
    
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN, prompt)

@tool
def invoke_custom_agent_query(agent_type: str, question: str) -> Dict[str, Any]:
    """Invoke a specific agent with a custom question. agent_type: health, performance, security, lifecycle"""
    agent_map = {
        'health': HEALTH_AGENT_ARN,
        'performance': PERFORMANCE_AGENT_ARN,
        'security': SECURITY_AGENT_ARN,
        'lifecycle': LIFECYCLE_AGENT_ARN
    }
    agent_arn = agent_map.get(agent_type.lower())
    if not agent_arn:
        return {'error': f"Unknown agent type: {agent_type}. Use: health, performance, security, lifecycle"}
    
    return invoke_agent_runtime(agent_arn, question)

# ===== SNS NOTIFICATION TOOL =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    try:
        sns_client = boto3.client('sns', region_name=AWS_REGION)
        response = sns_client.list_topics()
        topic_arn = None
        
        for topic in response.get('Topics', []):
            if topic['TopicArn'].endswith(f":{SNS_TOPIC_NAME}"):
                topic_arn = topic['TopicArn']
                break
        
        if not topic_arn:
            return {'status': 'error', 'error': f"SNS topic '{SNS_TOPIC_NAME}' not found"}
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted_message = f"""
SQL SERVER SUPERVISOR ALERT
============================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by AgentCore Supervisor Agent
"""
        
        sns_subject = f"[{severity}] {subject}"[:100]
        response = sns_client.publish(
            TopicArn=topic_arn,
            Subject=sns_subject,
            Message=formatted_message
        )
        
        return {
            'status': 'success',
            'message_id': response.get('MessageId'),
            'severity': severity
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

@tool
def generate_daily_report() -> Dict[str, Any]:
    """Generate comprehensive daily operational report from all agents"""
    try:
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'health_check': invoke_health_check(),
            'performance_analysis': invoke_performance_analysis(),
            'security_audit': invoke_security_audit(),
            'lifecycle_check': invoke_lifecycle_check()
        }
        
        # Compile summary
        summary = f"""
DAILY SQL SERVER OPERATIONS REPORT
===================================
Generated: {report['timestamp']}

DATABASE HEALTH:
{report['health_check'].get('response', report['health_check'].get('error', 'N/A'))}

QUERY PERFORMANCE:
{report['performance_analysis'].get('response', report['performance_analysis'].get('error', 'N/A'))}

SECURITY AUDIT:
{report['security_audit'].get('response', report['security_audit'].get('error', 'N/A'))}

DATA LIFECYCLE:
{report['lifecycle_check'].get('response', report['lifecycle_check'].get('error', 'N/A'))}

---
End of Report
"""
        
        return {
            'status': 'success',
            'report': summary,
            'detailed_results': report
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# ===== AGENT CONFIGURATION =====

system_prompt = """You are the Supervisor Agent that orchestrates all SQL Server database management agents.

IMPORTANT: You have access to long-term memory that provides operational policies, user preferences, and findings from previous investigations. This context is injected into user messages inside <user_context> tags. Always check for and use this context when answering questions about policies, preferences, or past findings.

CRITICAL: BEFORE invoking any tools, you must:
1. Read the user's question carefully
2. Check if the answer is available in the <user_context> memory context
3. Check if ANY tool description explicitly mentions what they're asking for
4. If the answer is in memory context, respond using that information without invoking tools
5. If NO tool mentions it and no memory context covers it, immediately respond that you don't have that capability
6. Only invoke tools when their description directly covers the request

You coordinate 4 specialized agents:
1. **Database Health Agent** - CloudWatch metrics, Performance Insights (CPU, memory, connections, database load, IOPS, latency)
2. **Query Performance Agent** - Query Store + DMVs (slow queries, blocking, missing indexes, query plans)
3. **Security Audit Agent** - RDS API + CloudWatch Logs (encryption, RDS events, CloudTrail, failed logins, security settings)
4. **Data Lifecycle Agent** - CloudWatch + DMVs (storage trends, IOPS/throughput/latency, TempDB analysis, table sizes, backups)

Available tools:

Agent Coordination:
- invoke_health_check: CPU, memory, connections, database load, storage metrics, IOPS, latency, wait events
- invoke_performance_analysis: Query Store analysis, slow queries, blocking, missing indexes, query plans, wait statistics
- invoke_security_audit: TDE encryption, backup encryption, failed logins, RDS events, CloudTrail changes, security settings
- invoke_lifecycle_check: Comprehensive storage analysis (all 25 tools - use sparingly)
- invoke_backup_check: Backup status only (targeted, fast)
- invoke_tempdb_analysis: TempDB bottleneck analysis only (targeted)
- invoke_custom_agent_query: Ask specific agent a custom question
- generate_daily_report: Compile insights from all agents

Reporting & Alerting:
- send_email_notification: Send consolidated alerts

STOP CHECKPOINT: Before invoking any tool, ask yourself:
"Does this tool's description explicitly mention what the user is asking for?"
If NO, don't invoke it. Respond that you don't have that capability.

When answering questions:
1. Analyze the user's question to understand what information they need
2. Review each available tool's description carefully
3. If no tool explicitly mentions the requested information, immediately respond:
   "I don't have a tool that provides [requested information]. My available tools cover: [list relevant capabilities]"
4. **BEFORE invoking any tool, announce:** "I'll use the [Agent Name] to check [what you're checking]..."
5. Be precise - if a user asks for "tempdb usage" and no tool mentions "tempdb", respond immediately that you don't have that capability
6. Never invoke tools hoping they might have the information
7. Only invoke tools when you're certain they can answer the question
8. If a tool fails, inform the user and suggest alternatives
9. Synthesize responses into a clear, actionable answer
10. **ONLY send email alerts when explicitly requested in the user's prompt**

Question routing examples:
- "Why is the database slow?" → Announce: "I'll use the Database Health Agent and Query Performance Agent to investigate..." → invoke_health_check + invoke_performance_analysis
- "What's my CPU usage?" → Announce: "I'll use the Database Health Agent to check CPU metrics..." → invoke_health_check
- "Which queries are slowest?" → Announce: "I'll use the Query Performance Agent to analyze query performance..." → invoke_performance_analysis
- "Any failed logins?" → Announce: "I'll use the Security Audit Agent to check for failed login attempts..." → invoke_security_audit
- "Check backup status" → Announce: "I'll use the Data Lifecycle Agent to check backup status..." → invoke_backup_check (targeted, fast)
- "Analyze TempDB" → Announce: "I'll use the Data Lifecycle Agent to analyze TempDB..." → invoke_tempdb_analysis (targeted)
- "Full storage analysis" → Announce: "I'll use the Data Lifecycle Agent for comprehensive storage analysis..." → invoke_lifecycle_check (comprehensive, slow)
- "Any RDS events?" → Announce: "I'll use the Security Audit Agent to check RDS events..." → invoke_security_audit
- "What is tempdb usage?" → "I don't have a tool for tempdb-specific metrics"
- "What is SQL Server version?" → "I don't have a tool to retrieve SQL Server version"
- "Give me a complete report" → generate_daily_report"""


_tools = [
        check_agent_configuration,
        invoke_health_check,
        invoke_performance_analysis,
        invoke_security_audit,
        invoke_lifecycle_check,
        invoke_backup_check,
        invoke_tempdb_analysis,
        invoke_custom_agent_query,
        generate_daily_report,
        send_email_notification
    ]

agent = Agent(
    system_prompt=system_prompt,
    model=model,

    tools=_tools
)

@app.entrypoint
def supervisor_agent(payload, context=None):
    """Invoke the Supervisor Agent with a payload"""
    user_input = payload.get("prompt", "")
    session_id = getattr(context, 'session_id', None) or payload.get("session_id", "default")
    sm = build_session_manager(session_id=session_id)
    if sm:
        with sm:
            a = Agent(system_prompt=agent.system_prompt, model=model, session_manager=sm, tools=_tools)
            response = a(user_input)
            return response.message['content'][0]['text']
    else:
        response = agent(user_input)
        return response.message['content'][0]['text']

if __name__ == "__main__":
    if os.getenv("LOCAL_TESTING"):
        app.run(port=9005)
    else:
        app.run()

