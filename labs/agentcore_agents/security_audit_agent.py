# Updated: 2026-03-15
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import boto3
import pymssql
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

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
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')

# Helper functions
def get_db_connection():
    """Get database connection using credentials from Secrets Manager"""
    try:
        secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
        secret = secrets_client.get_secret_value(SecretId=DB_SECRET_ID)
        creds = json.loads(secret['SecretString'])
        
        conn = pymssql.connect(
            server=creds['host'],
            user=creds['username'],
            password=creds['password'],
            port=creds['port'],
            database='master'
        )
        return conn
    except Exception as e:
        raise Exception(f"Error connecting to database: {str(e)}")

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.3
)

# ===== ENCRYPTION & DATA PROTECTION =====

@tool
def check_tde_status() -> Dict[str, Any]:
    """Check Transparent Data Encryption (TDE) status per database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            d.name AS database_name,
            CASE WHEN dek.encryption_state IS NOT NULL THEN 1 ELSE 0 END AS tde_enabled,
            dek.encryption_state,
            dek.percent_complete,
            dek.key_algorithm,
            dek.key_length
        FROM sys.databases d
        LEFT JOIN sys.dm_database_encryption_keys dek ON d.database_id = dek.database_id
        WHERE d.database_id > 4  -- Exclude system databases
        ORDER BY d.name
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        enabled_count = sum(1 for r in results if r['tde_enabled'])
        
        return {
            'databases': results,
            'total_databases': len(results),
            'tde_enabled_count': enabled_count,
            'tde_disabled_count': len(results) - enabled_count
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def check_backup_encryption() -> Dict[str, Any]:
    """Check if RDS storage and backups are encrypted"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        
        # Get DB instance info
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = db_response['DBInstances'][0]
        
        # Get recent snapshots
        snapshot_response = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=DB_INSTANCE_ID,
            MaxRecords=10
        )
        
        snapshots = []
        for snapshot in snapshot_response.get('DBSnapshots', []):
            snapshots.append({
                'snapshot_id': snapshot['DBSnapshotIdentifier'],
                'encrypted': snapshot['Encrypted'],
                'kms_key_id': snapshot.get('KmsKeyId', 'N/A'),
                'snapshot_create_time': snapshot['SnapshotCreateTime'].isoformat(),
                'snapshot_type': snapshot['SnapshotType']
            })
        
        encrypted_count = sum(1 for s in snapshots if s['encrypted'])
        
        return {
            'storage_encrypted': db_instance['StorageEncrypted'],
            'kms_key_id': db_instance.get('KmsKeyId', 'N/A'),
            'snapshots': snapshots,
            'total_snapshots': len(snapshots),
            'encrypted_snapshots': encrypted_count,
            'unencrypted_snapshots': len(snapshots) - encrypted_count
        }
    except Exception as e:
        return {'error': str(e)}

# ===== AUDITING & COMPLIANCE =====

@tool
def get_failed_login_attempts(hours_back: int = 168) -> Dict[str, Any]:
    """Get failed login attempts from CloudWatch Logs (default: 7 days)"""
    try:
        logs_client = boto3.client('logs', region_name=AWS_REGION)
        log_group = f"/aws/rds/instance/{DB_INSTANCE_ID}/error"
        
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp() * 1000)
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        query = """
        fields @timestamp, @message
        | filter @message like /Login failed/
        | sort @timestamp desc
        | limit 100
        """
        
        query_response = logs_client.start_query(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=query
        )
        
        query_id = query_response['queryId']
        
        # Poll for results
        import time
        for _ in range(10):
            time.sleep(1)
            result = logs_client.get_query_results(queryId=query_id)
            if result['status'] == 'Complete':
                return {
                    'failed_logins': result['results'],
                    'count': len(result['results']),
                    'hours_analyzed': hours_back
                }
        
        return {'error': 'Query timeout', 'query_id': query_id}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_rds_events(hours_back: int = 168) -> Dict[str, Any]:
    """Get RDS events including configuration changes (default: 7 days)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        end_time = datetime.now(timezone.utc)
        
        response = rds_client.describe_events(
            SourceIdentifier=DB_INSTANCE_ID,
            SourceType='db-instance',
            StartTime=start_time,
            EndTime=end_time
        )
        
        events = []
        for event in response.get('Events', []):
            events.append({
                'date': event['Date'].isoformat(),
                'message': event['Message'],
                'source_type': event.get('SourceType'),
                'source_identifier': event.get('SourceIdentifier'),
                'event_categories': event.get('EventCategories', [])
            })
        
        # Filter for configuration-related events
        config_events = [e for e in events if any(
            keyword in e['message'].lower() 
            for keyword in ['parameter', 'option', 'configuration', 'modified', 'changed']
        )]
        
        return {
            'all_events': events,
            'total_events': len(events),
            'configuration_events': config_events,
            'configuration_event_count': len(config_events),
            'hours_analyzed': hours_back
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def get_configuration_changes_from_cloudtrail(hours_back: int = 168) -> Dict[str, Any]:
    """Get configuration changes from CloudTrail (default: 7 days)"""
    try:
        cloudtrail_client = boto3.client('cloudtrail', region_name=AWS_REGION)
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Events to track
        event_names = [
            'ModifyDBParameterGroup',
            'ModifyOptionGroup',
            'ModifyDBInstance',
            'ResetDBParameterGroup',
            'CreateDBParameterGroup',
            'CreateOptionGroup'
        ]
        
        all_changes = []
        
        for event_name in event_names:
            response = cloudtrail_client.lookup_events(
                LookupAttributes=[
                    {
                        'AttributeKey': 'EventName',
                        'AttributeValue': event_name
                    }
                ],
                StartTime=start_time,
                MaxResults=50
            )
            
            for event in response.get('Events', []):
                cloud_trail_event = json.loads(event['CloudTrailEvent'])
                
                change_detail = {
                    'event_time': event['EventTime'].isoformat(),
                    'event_name': event['EventName'],
                    'username': event.get('Username'),
                    'source_ip': cloud_trail_event.get('sourceIPAddress'),
                    'user_agent': cloud_trail_event.get('userAgent'),
                    'request_parameters': cloud_trail_event.get('requestParameters', {}),
                    'response_elements': cloud_trail_event.get('responseElements', {})
                }
                
                all_changes.append(change_detail)
        
        # Sort by time
        all_changes.sort(key=lambda x: x['event_time'], reverse=True)
        
        return {
            'configuration_changes': all_changes,
            'total_changes': len(all_changes),
            'hours_analyzed': hours_back,
            'change_types': list(set([c['event_name'] for c in all_changes]))
        }
    except Exception as e:
        return {'error': str(e)}

# ===== RDS SECURITY CONFIGURATION =====

@tool
def check_rds_security_settings() -> Dict[str, Any]:
    """Check RDS security settings (public accessibility, VPC, security groups, IAM auth, deletion protection)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = response['DBInstances'][0]
        
        # Extract security settings
        security_settings = {
            'publicly_accessible': db_instance['PubliclyAccessible'],
            'vpc_id': db_instance['DBSubnetGroup']['VpcId'],
            'subnet_group': db_instance['DBSubnetGroup']['DBSubnetGroupName'],
            'security_groups': [sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']],
            'iam_database_authentication_enabled': db_instance.get('IAMDatabaseAuthenticationEnabled', False),
            'storage_encrypted': db_instance['StorageEncrypted'],
            'deletion_protection': db_instance.get('DeletionProtection', False),
            'backup_retention_period': db_instance['BackupRetentionPeriod'],
            'multi_az': db_instance['MultiAZ'],
            'auto_minor_version_upgrade': db_instance['AutoMinorVersionUpgrade']
        }
        
        # Security recommendations
        issues = []
        if security_settings['publicly_accessible']:
            issues.append('Database is publicly accessible')
        if not security_settings['iam_database_authentication_enabled']:
            issues.append('IAM database authentication not enabled')
        if not security_settings['storage_encrypted']:
            issues.append('Storage encryption not enabled')
        if not security_settings['deletion_protection']:
            issues.append('Deletion protection not enabled')
        if security_settings['backup_retention_period'] < 7:
            issues.append(f"Backup retention period is only {security_settings['backup_retention_period']} days")
        if not security_settings['auto_minor_version_upgrade']:
            issues.append('Auto minor version upgrade not enabled')
        
        return {
            'security_settings': security_settings,
            'issues': issues,
            'issue_count': len(issues),
            'security_score': max(0, 100 - (len(issues) * 15))
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def check_rds_audit_settings() -> Dict[str, Any]:
    """Check RDS audit settings (SQL Server Audit/DAS, backup restore options)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        
        # Get DB instance details
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = response['DBInstances'][0]
        
        # Get option groups (contains SQL Server Audit settings)
        option_group_name = db_instance['OptionGroupMemberships'][0]['OptionGroupName']
        option_response = rds_client.describe_option_groups(OptionGroupName=option_group_name)
        
        options = option_response['OptionGroupsList'][0]['Options']
        
        # Check for SQL Server Audit (SQLSERVER_AUDIT)
        audit_enabled = False
        audit_settings = {}
        
        for option in options:
            if option['OptionName'] == 'SQLSERVER_AUDIT':
                audit_enabled = True
                audit_settings = {
                    'option_name': option['OptionName'],
                    'port': option.get('Port'),
                    'vpc_security_groups': option.get('VpcSecurityGroupMemberships', []),
                    'option_settings': {s['Name']: s['Value'] for s in option.get('OptionSettings', [])}
                }
        
        # Get parameter group (contains backup/restore settings)
        param_group_name = db_instance['DBParameterGroups'][0]['DBParameterGroupName']
        param_response = rds_client.describe_db_parameters(
            DBParameterGroupName=param_group_name,
            Source='user'
        )
        
        # Check for backup/restore related parameters
        backup_restore_params = {}
        for param in param_response.get('Parameters', []):
            if 'backup' in param['ParameterName'].lower() or 'restore' in param['ParameterName'].lower():
                backup_restore_params[param['ParameterName']] = param.get('ParameterValue', 'default')
        
        return {
            'sql_server_audit_enabled': audit_enabled,
            'audit_settings': audit_settings if audit_enabled else None,
            'option_group_name': option_group_name,
            'parameter_group_name': param_group_name,
            'backup_restore_parameters': backup_restore_params,
            'all_options': [opt['OptionName'] for opt in options]
        }
    except Exception as e:
        return {'error': str(e)}

# ===== MONITORING & ALERTING =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send a security alert via SNS. Severity: INFO, WARNING, CRITICAL"""
    try:
        topic_name = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
        
        sns_client = boto3.client('sns', region_name=AWS_REGION)
        response = sns_client.list_topics()
        topic_arn = None
        
        for topic in response.get('Topics', []):
            if topic['TopicArn'].endswith(f":{topic_name}"):
                topic_arn = topic['TopicArn']
                break
        
        if not topic_arn:
            return {'status': 'error', 'error': f"SNS topic '{topic_name}' not found"}
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted_message = f"""
SQL SERVER SECURITY ALERT
=========================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by AgentCore Security Audit Agent
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

# ===== AGENT CONFIGURATION =====

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
- check_rds_security_settings: Public accessibility, VPC, IAM auth, deletion protection, backup retention (RDS API)

**Alerting:**
- send_email_notification: Send security alerts via SNS

**Investigation workflow:**

1. **Encryption Audit**:
   - Use check_tde_status for database-level encryption
   - Use check_backup_encryption for storage and snapshot encryption

2. **Compliance Audit**:
   - Use check_rds_audit_settings to verify SQL Server Audit (DAS) is enabled
   - Check get_failed_login_attempts for suspicious activity
   - Use get_rds_events to see recent configuration changes
   - Use get_configuration_changes_from_cloudtrail for detailed change tracking (who made changes)

3. **Infrastructure Security**:
   - Use check_rds_security_settings for RDS-level security
   - Verify VPC, security groups, IAM auth, deletion protection

4. **ONLY send email alerts when explicitly requested in the user's prompt**

**Response format:**

## Security Score
- Overall: [X/100]
- Critical Issues: [count]

## Encryption Status
- TDE Enabled: [X/Y databases]
- Storage Encryption: [YES/NO]
- Backup Encryption: [X/Y snapshots]

## Auditing & Compliance
- SQL Server Audit (DAS): [ENABLED/DISABLED]
- Failed Logins (24h): [count]
- Configuration Changes (24h): [count]
- Recent Changes: [list]

## RDS Security
- Publicly Accessible: [YES/NO]
- IAM Auth: [YES/NO]
- Deletion Protection: [YES/NO]
- Backup Retention: [X days]
- Multi-AZ: [YES/NO]

## Critical Issues
1. **Issue**: [Description]
2. **Risk**: [High/Medium/Low]
3. **Recommendation**: [Action]

## Action Items
1. **Critical**: [Immediate security fixes]
2. **High**: [Important security improvements]
3. **Medium**: [Security enhancements]"""

_tools = [
        # Encryption & Data Protection
        check_tde_status,
        check_backup_encryption,
        # Auditing & Compliance
        get_failed_login_attempts,
        get_rds_events,
        get_configuration_changes_from_cloudtrail,
        check_rds_audit_settings,
        # RDS Security Configuration
        check_rds_security_settings,
        # Alerting
        send_email_notification
    ]

agent = Agent(
    system_prompt=system_prompt,
    model=model,

    tools=_tools
)

@app.entrypoint
def security_audit_agent(payload, context=None):
    """Invoke the Security Audit Agent with a payload"""
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
        app.run(port=9004)
    else:
        app.run()
