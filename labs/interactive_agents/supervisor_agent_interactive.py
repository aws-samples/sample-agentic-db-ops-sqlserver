# Updated: 2026-03-15
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Import local agents for testing
from database_health_agent_interactive import agent as health_agent
from query_performance_agent_interactive import agent as performance_agent
from security_audit_agent_interactive import agent as security_agent
from data_lifecycle_agent_interactive import agent as lifecycle_agent
try:
    from actions_agent_interactive import agent as actions_agent
except ImportError:
    actions_agent = None

# Configuration from environment variables.
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.3
)

# Helper function to invoke other agents
def invoke_agent_runtime(agent_name: str, prompt: str) -> Dict[str, Any]:
    """Invoke local agent directly for testing"""
    agents = {
        'database_health_agent': health_agent,
        'query_performance_agent': performance_agent,
        'security_audit_agent': security_agent,
        'data_lifecycle_agent': lifecycle_agent,
        'actions_agent': actions_agent
    }
    try:
        agent = agents.get(agent_name.lower())
        if not agent:
            return {'error': f"Agent '{agent_name}' not found"}
        
        response = agent(prompt)
        return {'response': response.message['content'][0]['text']}
    except Exception as e:
        return {'error': str(e)}

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
    
    return invoke_agent_runtime('database_health_agent', prompt)

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
    
    return invoke_agent_runtime('query_performance_agent', prompt)

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
    
    return invoke_agent_runtime('security_audit_agent', prompt)

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
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_backup_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for backup status"""
    prompt = """Check backup status only:
    - Use check_backup_status tool
    - Backup retention period
    - Recent snapshots
    - Latest restorable time
    
    Report backup compliance."""
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_tempdb_analysis() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for TempDB analysis"""
    prompt = """Analyze TempDB only:
    - Use analyze_tempdb_bottleneck tool
    - TempDB size and usage
    - Configuration issues
    - Contention and I/O problems
    
    Report TempDB bottlenecks."""
    
    return invoke_agent_runtime('data_lifecycle_agent', prompt)

@tool
def invoke_custom_agent_query(agent_name: str, question: str) -> Dict[str, Any]:
    """Invoke a specific agent with a custom question"""
    return invoke_agent_runtime(agent_name, question)

@tool
def invoke_actions_agent(action_request: str) -> Dict[str, Any]:
    """Invoke the Actions Agent to execute ONE specific database optimization action.

    IMPORTANT: Send ONE action at a time. Do NOT batch multiple actions in a single call.
    Call this tool multiple times sequentially if you need multiple actions executed.

    The Actions Agent can: create indexes, update statistics, rebuild/reorganize indexes,
    and force/unforce query plans.

    All MEDIUM risk actions (index creation) require human approval via email before execution.

    Examples of good action requests:
    - "Create index: <the exact CREATE INDEX statement from suggest_indexes for the offending query>"
    - "Update statistics on <table> table"
    - "Rebuild index <index name> on <table>"

    Examples of BAD requests (do NOT do this):
    - "Fix all the slow queries" (too broad)
    - "Create 5 indexes" (batched — send one at a time)

    Args:
        action_request: ONE specific action with the exact SQL or parameters needed
    """
    if actions_agent is None:
        return {'error': 'Actions Agent not available. Ensure actions_agent_interactive.py is in the same directory.'}
    return invoke_agent_runtime('actions_agent', action_request)

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

system_prompt = """You are the Supervisor Agent for SQL Server database operations. You are the ONLY reasoner in this system.

The diagnostic agents you invoke are tool executors — they return RAW DATA (tool outputs), not
judgments. They do NOT assign severity, rank findings, or recommend anything. ALL interpretation is
your job: read the raw metrics, assign severity, identify the root cause from the data, and decide actions.

RULES:
1. DO NOT GUESS. Reason only from the raw data the agents return.
2. Respond in under 150 words. Format: Root Cause → Evidence → Action.
3. Invoke actions_agent at most ONCE with ONE specific action — the single highest-impact fix.
4. Send at most ONE email notification per interaction — only for genuine critical alerts.
5. Do NOT ask "Would you like me to...?" — either act (if authorized) or state the recommendation.
6. Invoke only the diagnostic agent(s) the symptom points to. Do not run all agents unless a full report is requested.

Severity thresholds (you apply these — the agents do not):
- CRITICAL: CPU >90% OR AAS >8 OR connections near max OR freeable memory <1 GB
- WARNING: CPU >70% OR AAS >4 OR memory declining OR connections >70% of max
- INFO: all metrics within normal ranges

You coordinate 5 agents:
1. Database Health Agent — CloudWatch + Performance Insights metrics
2. Query Performance Agent — Query Store + DMVs (slow queries, missing indexes)
3. Security Audit Agent — Encryption, logins, RDS events, CloudTrail
4. Data Lifecycle Agent — Storage, IOPS, TempDB, backups
5. Actions Agent — Execute ONE approved optimization

Tools:
- invoke_health_check: CPU, memory, connections, storage, IOPS, latency, wait events
- invoke_performance_analysis: Slow queries, blocking, missing indexes, query plans
- invoke_security_audit: Encryption, failed logins, RDS events, CloudTrail
- invoke_lifecycle_check: Full storage analysis (use sparingly)
- invoke_backup_check: Backup status only
- invoke_tempdb_analysis: TempDB only
- invoke_custom_agent_query: Custom question to a specific agent
- invoke_actions_agent: Execute ONE fix (call ONCE)
- generate_daily_report: All-agent summary
- send_email_notification: ONE consolidated alert

Workflow:
1. Route to the right diagnostic agent(s)
2. Read their findings
3. State root cause (from the data, not speculation)
4. If fix needed: invoke actions_agent ONCE
5. Respond concisely

Routing:
- CPU/memory/connections → invoke_health_check
- Slow queries/indexes → invoke_performance_analysis
- Security → invoke_security_audit
- Storage/backups → invoke_backup_check or invoke_lifecycle_check
- Fix needed → invoke_actions_agent (ONE action)"""


agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        invoke_health_check,
        invoke_performance_analysis,
        invoke_security_audit,
        invoke_lifecycle_check,
        invoke_backup_check,
        invoke_tempdb_analysis,
        invoke_custom_agent_query,
        invoke_actions_agent,
        generate_daily_report,
        send_email_notification
    ]
)

if __name__ == "__main__":
    print("Supervisor Agent - Coordinate all database operations and generate reports.")
    print("Type 'exit' or 'quit' to end.\n")
    
    while True:
        prompt = input("Your prompt: ")
        
        if prompt.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
        
        if prompt.strip():
            response = agent(prompt)
            print(response.message['content'][0]['text'])
            print()

