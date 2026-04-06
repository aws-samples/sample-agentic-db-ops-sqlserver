import boto3
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from strands import tool
from config.settings import DB_INSTANCE_ID, DB_SECRET_ID, AWS_REGION, SNS_TOPIC_NAME
from tools.shared_utils import db_cursor, fetch_all, send_notification


# ===== ENCRYPTION & DATA PROTECTION =====

@tool
def check_tde_status() -> Dict[str, Any]:
    """Check Transparent Data Encryption (TDE) status per database"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT d.name AS database_name,
                   CASE WHEN dek.encryption_state IS NOT NULL THEN 1 ELSE 0 END AS tde_enabled,
                   dek.encryption_state, dek.percent_complete, dek.key_algorithm, dek.key_length
            FROM sys.databases d
            LEFT JOIN sys.dm_database_encryption_keys dek ON d.database_id = dek.database_id
            WHERE d.database_id > 4
            ORDER BY d.name
            """)
            results = fetch_all(cursor)
        enabled_count = sum(1 for r in results if r['tde_enabled'])
        return {'databases': results, 'total_databases': len(results),
                'tde_enabled_count': enabled_count, 'tde_disabled_count': len(results) - enabled_count}
    except Exception as e:
        return {'error': str(e)}


@tool
def check_backup_encryption() -> Dict[str, Any]:
    """Check if RDS storage and backups are encrypted"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = db_response['DBInstances'][0]
        snapshot_response = rds_client.describe_db_snapshots(DBInstanceIdentifier=DB_INSTANCE_ID, MaxRecords=10)
        snapshots = []
        for s in snapshot_response.get('DBSnapshots', []):
            snapshots.append({
                'snapshot_id': s['DBSnapshotIdentifier'], 'encrypted': s['Encrypted'],
                'kms_key_id': s.get('KmsKeyId', 'N/A'),
                'snapshot_create_time': s['SnapshotCreateTime'].isoformat(), 'snapshot_type': s['SnapshotType']
            })
        encrypted_count = sum(1 for s in snapshots if s['encrypted'])
        return {
            'storage_encrypted': db_instance['StorageEncrypted'], 'kms_key_id': db_instance.get('KmsKeyId', 'N/A'),
            'snapshots': snapshots, 'total_snapshots': len(snapshots),
            'encrypted_snapshots': encrypted_count, 'unencrypted_snapshots': len(snapshots) - encrypted_count
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
        query_response = logs_client.start_query(
            logGroupName=log_group, startTime=start_time, endTime=end_time,
            queryString="fields @timestamp, @message | filter @message like /Login failed/ | sort @timestamp desc | limit 100"
        )
        query_id = query_response['queryId']
        for _ in range(10):
            time.sleep(1)
            result = logs_client.get_query_results(queryId=query_id)
            if result['status'] == 'Complete':
                return {'failed_logins': result['results'], 'count': len(result['results']), 'hours_analyzed': hours_back}
        return {'error': 'Query timeout', 'query_id': query_id}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_rds_events(hours_back: int = 168) -> Dict[str, Any]:
    """Get RDS events including configuration changes (default: 7 days)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_events(
            SourceIdentifier=DB_INSTANCE_ID, SourceType='db-instance',
            StartTime=datetime.now(timezone.utc) - timedelta(hours=hours_back),
            EndTime=datetime.now(timezone.utc)
        )
        events = [{'date': e['Date'].isoformat(), 'message': e['Message'],
                    'source_type': e.get('SourceType'), 'source_identifier': e.get('SourceIdentifier'),
                    'event_categories': e.get('EventCategories', [])} for e in response.get('Events', [])]
        config_events = [e for e in events if any(
            kw in e['message'].lower() for kw in ['parameter', 'option', 'configuration', 'modified', 'changed'])]
        return {'all_events': events, 'total_events': len(events),
                'configuration_events': config_events, 'configuration_event_count': len(config_events), 'hours_analyzed': hours_back}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_configuration_changes_from_cloudtrail(hours_back: int = 168) -> Dict[str, Any]:
    """Get configuration changes from CloudTrail (default: 7 days)"""
    try:
        cloudtrail_client = boto3.client('cloudtrail', region_name=AWS_REGION)
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        event_names = ['ModifyDBParameterGroup', 'ModifyOptionGroup', 'ModifyDBInstance',
                       'ResetDBParameterGroup', 'CreateDBParameterGroup', 'CreateOptionGroup']
        all_changes = []
        for event_name in event_names:
            response = cloudtrail_client.lookup_events(
                LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': event_name}],
                StartTime=start_time, MaxResults=50
            )
            for event in response.get('Events', []):
                ct_event = json.loads(event['CloudTrailEvent'])
                all_changes.append({
                    'event_time': event['EventTime'].isoformat(), 'event_name': event['EventName'],
                    'username': event.get('Username'), 'source_ip': ct_event.get('sourceIPAddress'),
                    'user_agent': ct_event.get('userAgent'),
                    'request_parameters': ct_event.get('requestParameters', {}),
                    'response_elements': ct_event.get('responseElements', {})
                })
        all_changes.sort(key=lambda x: x['event_time'], reverse=True)
        return {'configuration_changes': all_changes, 'total_changes': len(all_changes),
                'hours_analyzed': hours_back, 'change_types': list(set(c['event_name'] for c in all_changes))}
    except Exception as e:
        return {'error': str(e)}


@tool
def check_rds_security_settings() -> Dict[str, Any]:
    """Check RDS security settings (public accessibility, VPC, security groups, IAM auth, deletion protection)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = response['DBInstances'][0]
        settings = {
            'publicly_accessible': db['PubliclyAccessible'],
            'vpc_id': db['DBSubnetGroup']['VpcId'], 'subnet_group': db['DBSubnetGroup']['DBSubnetGroupName'],
            'security_groups': [sg['VpcSecurityGroupId'] for sg in db['VpcSecurityGroups']],
            'iam_database_authentication_enabled': db.get('IAMDatabaseAuthenticationEnabled', False),
            'storage_encrypted': db['StorageEncrypted'], 'deletion_protection': db.get('DeletionProtection', False),
            'backup_retention_period': db['BackupRetentionPeriod'], 'multi_az': db['MultiAZ'],
            'auto_minor_version_upgrade': db['AutoMinorVersionUpgrade']
        }
        issues = []
        if settings['publicly_accessible']: issues.append('Database is publicly accessible')
        if not settings['iam_database_authentication_enabled']: issues.append('IAM database authentication not enabled')
        if not settings['storage_encrypted']: issues.append('Storage encryption not enabled')
        if not settings['deletion_protection']: issues.append('Deletion protection not enabled')
        if settings['backup_retention_period'] < 7: issues.append(f"Backup retention period is only {settings['backup_retention_period']} days")
        if not settings['auto_minor_version_upgrade']: issues.append('Auto minor version upgrade not enabled')
        return {'security_settings': settings, 'issues': issues, 'issue_count': len(issues),
                'security_score': max(0, 100 - (len(issues) * 15))}
    except Exception as e:
        return {'error': str(e)}


@tool
def check_rds_audit_settings() -> Dict[str, Any]:
    """Check RDS audit settings (SQL Server Audit/DAS, backup restore options)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = response['DBInstances'][0]
        option_group_name = db['OptionGroupMemberships'][0]['OptionGroupName']
        option_response = rds_client.describe_option_groups(OptionGroupName=option_group_name)
        options = option_response['OptionGroupsList'][0]['Options']
        audit_enabled = False
        audit_settings = {}
        for option in options:
            if option['OptionName'] == 'SQLSERVER_AUDIT':
                audit_enabled = True
                audit_settings = {
                    'option_name': option['OptionName'], 'port': option.get('Port'),
                    'vpc_security_groups': option.get('VpcSecurityGroupMemberships', []),
                    'option_settings': {s['Name']: s['Value'] for s in option.get('OptionSettings', [])}
                }
        param_group_name = db['DBParameterGroups'][0]['DBParameterGroupName']
        param_response = rds_client.describe_db_parameters(DBParameterGroupName=param_group_name, Source='user')
        backup_restore_params = {p['ParameterName']: p.get('ParameterValue', 'default')
                                  for p in param_response.get('Parameters', [])
                                  if 'backup' in p['ParameterName'].lower() or 'restore' in p['ParameterName'].lower()}
        return {
            'sql_server_audit_enabled': audit_enabled, 'audit_settings': audit_settings if audit_enabled else None,
            'option_group_name': option_group_name, 'parameter_group_name': param_group_name,
            'backup_restore_parameters': backup_restore_params, 'all_options': [opt['OptionName'] for opt in options]
        }
    except Exception as e:
        return {'error': str(e)}


# ===== SNS =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send a security alert via SNS. Severity: INFO, WARNING, CRITICAL"""
    return send_notification(subject, message, severity, agent_name="Security Audit Agent")
