import boto3
import json
from datetime import datetime, timezone
from typing import Dict, Any
from strands import tool
from config.settings import (
    AWS_REGION, SNS_TOPIC_NAME, DB_INSTANCE_ID,
    HEALTH_AGENT_ARN, PERFORMANCE_AGENT_ARN, SECURITY_AGENT_ARN, LIFECYCLE_AGENT_ARN
)
from tools.shared_utils import send_notification


def invoke_agent_runtime(agent_arn: str, prompt: str) -> Dict[str, Any]:
    if not agent_arn:
        return {'error': 'Agent ARN not configured'}
    agent_core_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)
    payload = json.dumps({"prompt": prompt}).encode()
    response = agent_core_client.invoke_agent_runtime(agentRuntimeArn=agent_arn, payload=payload)
    if "text/event-stream" in response.get("contentType", ""):
        content = []
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    content.append(line[6:])
        return {'response': "\n".join(content)}
    elif response.get("contentType") == "application/json":
        content = [chunk.decode('utf-8') for chunk in response.get("response", [])]
        return {'response': json.loads(''.join(content))}
    return {'response': str(response)}


@tool
def check_agent_configuration() -> Dict[str, Any]:
    """Check if agent ARNs are configured"""
    return {
        'health_agent_arn': HEALTH_AGENT_ARN or 'NOT SET',
        'performance_agent_arn': PERFORMANCE_AGENT_ARN or 'NOT SET',
        'security_agent_arn': SECURITY_AGENT_ARN or 'NOT SET',
        'lifecycle_agent_arn': LIFECYCLE_AGENT_ARN or 'NOT SET'
    }


@tool
def invoke_health_check() -> Dict[str, Any]:
    """Invoke Database Health Agent for comprehensive health check"""
    return invoke_agent_runtime(HEALTH_AGENT_ARN,
        "Provide a comprehensive health check including: CPU utilization, memory usage, database connections, database load, storage space, IOPS and latency. Identify any critical issues.")


@tool
def invoke_performance_analysis() -> Dict[str, Any]:
    """Invoke Query Performance Agent for performance analysis"""
    return invoke_agent_runtime(PERFORMANCE_AGENT_ARN,
        "Analyze query performance including: top CPU-consuming queries, wait statistics, slow running queries, blocking sessions, missing index recommendations. Identify performance bottlenecks.")


@tool
def invoke_security_audit() -> Dict[str, Any]:
    """Invoke Security Audit Agent for security review"""
    return invoke_agent_runtime(SECURITY_AGENT_ARN,
        "Perform security audit including: TDE encryption status, backup encryption, failed login attempts (last 7 days), RDS events and configuration changes, CloudTrail activity, RDS security settings. Identify security concerns.")


@tool
def invoke_lifecycle_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent for comprehensive storage and lifecycle review"""
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN,
        "Review data lifecycle including: storage usage and growth trends, IOPS/throughput/latency trends, storage type and upgrade recommendations, TempDB analysis, largest tables and indexes, backup status, fragmentation status. Identify storage optimization opportunities.")


@tool
def invoke_backup_check() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for backup status"""
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN,
        "Check backup status only: backup retention period, recent snapshots, latest restorable time. Report backup compliance.")


@tool
def invoke_tempdb_analysis() -> Dict[str, Any]:
    """Invoke Data Lifecycle Agent specifically for TempDB analysis"""
    return invoke_agent_runtime(LIFECYCLE_AGENT_ARN,
        "Analyze TempDB only: TempDB size and usage, configuration issues, contention and I/O problems. Report TempDB bottlenecks.")


@tool
def invoke_custom_agent_query(agent_type: str, question: str) -> Dict[str, Any]:
    """Invoke a specific agent with a custom question. agent_type: health, performance, security, lifecycle"""
    agent_map = {'health': HEALTH_AGENT_ARN, 'performance': PERFORMANCE_AGENT_ARN,
                 'security': SECURITY_AGENT_ARN, 'lifecycle': LIFECYCLE_AGENT_ARN}
    agent_arn = agent_map.get(agent_type.lower())
    if not agent_arn:
        return {'error': f"Unknown agent type: {agent_type}. Use: health, performance, security, lifecycle"}
    return invoke_agent_runtime(agent_arn, question)


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
        return {'status': 'success', 'report': summary, 'detailed_results': report}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    return send_notification(subject, message, severity, agent_name="Supervisor Agent")
