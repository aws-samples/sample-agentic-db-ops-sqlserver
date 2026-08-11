# Updated: 2026-03-15
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
import json
import os
import io, sys
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
    """Invoke local agent directly - output suppressed"""
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
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            response = agent(prompt)
        finally:
            sys.stdout = old_stdout
        return {'response': response.message['content'][0]['text']}
    except Exception as e:
        sys.stdout = sys.__stdout__
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

system_prompt = """You are a Senior Database Operations Supervisor coordinating specialized diagnostic agents.

YOU DO NOT HAVE DIRECT ACCESS TO THE DATABASE OR CLOUDWATCH.
You ONLY get data by calling sub-agents. They return raw data. You do ALL reasoning.

SUB-AGENTS (what to ask each one):
- invoke_health_check: Ask about CPU, memory, connections, IOPS, wait events, top SQL, database load
- invoke_performance_analysis: Ask about slow queries, blocking, missing indexes, query plans, Query Store
- invoke_security_audit: Ask about encryption, failed logins, config changes
- invoke_lifecycle_check: Ask about storage, TempDB, backups, fragmentation
- invoke_custom_agent_query(agent_type, question): Ask a TARGETED follow-up question to any agent

HOW TO INVESTIGATE:

Step 1 - Pick the right agent(s) based on the symptom:
  - CPU high -> invoke_health_check FIRST (get wait events + top SQL)
  - Slow queries -> invoke_performance_analysis FIRST
  - Disk full -> invoke_lifecycle_check FIRST
  - Full report -> call all agents

Step 2 - Read the raw data. Ask targeted follow-ups:
  - Health says CPU wait is 70% and top SQL shows sp_ProductSalesReport?
    -> invoke_custom_agent_query("query_performance_agent", "Analyze sp_ProductSalesReport - check missing indexes and execution plan")
  - Performance says missing index on Orders(CustomerID)?
    -> invoke_custom_agent_query("query_performance_agent", "What other queries also scan Orders(CustomerID)?")

Step 3 - Correlate across agent responses:
  - 3 queries all scan the same table = 1 missing index (not 3 fixes)
  - High CPU + high logical reads + table scan = index problem (not CPU problem)
  - Blocking + idle session = investigate the idle session root cause

Step 4 - Present a unified plan:

## Findings
[Numbered facts - what each agent reported]

## Root Cause
[YOUR analysis connecting the dots across agents]

## Remediation Plan
| Step | Action | Fixes | Risk | Downtime |
|------|--------|-------|------|----------|

Shall I proceed?

RULES:
- Call invoke_custom_agent_query for TARGETED follow-ups (dont re-run the full check)
- Never recommend a fix without data from at least one agent confirming the problem
- Group related fixes - if multiple queries share a root cause, its ONE fix
- Show progress before agent calls so user knows you are working
- Do NOT echo raw agent responses to the user - summarize in your own words
- NEVER recommend or suggest killing sessions (KILL command). Instead, identify the root cause of why sessions are long-running or blocking, and recommend fixing that root cause (missing index, bad query design, application connection leak, etc). Flag problematic sessions for human awareness only.
- ALWAYS flag CRITICAL conditions at the TOP of your response regardless of what the user asked: storage near zero, connections near max, memory exhausted, replication lag. These are emergencies that override the users question.
- You MUST NOT send email notifications unless user explicitly says "send email" or "notify the team"
- If remediation requires MORE THAN ONE change: you MUST present the plan table and wait for explicit confirmation before calling invoke_actions_agent. Respond with "Here is my plan. Confirm to proceed:" followed by the plan table. This applies regardless of whether the user said "fix it" or "do it now".
- When correlating: check if different queries depend on the same table, same index, or same root cause. If so, group them as ONE fix and show the dependency in the plan."""


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
            print()

