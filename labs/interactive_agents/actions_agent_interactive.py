# Updated: 2026-07-31.
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# Configuration from environment variables
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
GUARDRAIL_ID = os.getenv('BEDROCK_GUARDRAIL_ID', '')  # Set to your guardrail ID
GUARDRAIL_VERSION = os.getenv('BEDROCK_GUARDRAIL_VERSION', 'DRAFT')

# Define the AI model with Bedrock Guardrail
model_config = {
    'model_id': os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    'region_name': AWS_REGION,
    'temperature': 0.3
}

# Attach guardrail if configured
if GUARDRAIL_ID:
    model_config['guardrail_id'] = GUARDRAIL_ID
    model_config['guardrail_version'] = GUARDRAIL_VERSION
    if __name__ == "__main__":
        print(f"✅ Bedrock Guardrail enabled: {GUARDRAIL_ID} (version: {GUARDRAIL_VERSION})")
elif __name__ == "__main__":
    print("⚠️  No Bedrock Guardrail configured. Set BEDROCK_GUARDRAIL_ID to enable.")

model = BedrockModel(**model_config)


def get_db_connection():
    """Get database connection using credentials from Secrets Manager"""
    try:
        secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
        secret = secrets_client.get_secret_value(SecretId=DB_SECRET_ID)
        creds = json.loads(secret['SecretString'])

        import pymssql
        conn = pymssql.connect(
            server=creds['host'],
            user=creds['username'],
            password=creds['password'],
            port=creds['port'],
            database='DBOpsLab'
        )
        return conn
    except Exception as e:
        raise Exception(f"Error connecting to database: {str(e)}")


# ===== RISK CLASSIFICATION =====

RISK_LEVELS = {
    'update_statistics': 'LOW',
    'unforce_query_plan': 'LOW',
    'reorganize_index': 'LOW',
    'create_index': 'MEDIUM',
    'force_query_plan': 'MEDIUM',
    'rebuild_index': 'MEDIUM',
    'drop_index': 'HIGH',
}


@tool
def classify_action_risk(action_name: str, details: str = "") -> Dict[str, Any]:
    """Classify the risk level of a proposed action.
    Returns risk level and whether human approval is required.
    
    Risk levels:
    - LOW: Auto-approved (update statistics, unforce plan)
    - MEDIUM: Requires human approval (create index, force plan)
    - HIGH: Requires human approval + confirmation (drop index, schema changes)
    """
    risk = RISK_LEVELS.get(action_name, 'HIGH')
    requires_approval = risk in ('MEDIUM', 'HIGH')

    return {
        'action': action_name,
        'risk_level': risk,
        'requires_approval': requires_approval,
        'details': details,
        'policy': {
            'LOW': 'Auto-approved. Safe to execute immediately.',
            'MEDIUM': 'Requires human approval before execution.',
            'HIGH': 'Requires human approval + written confirmation. High impact change.'
        }[risk]
    }


@tool
def request_human_approval(action_name: str, risk_level: str, description: str, sql_statement: str = "") -> Dict[str, Any]:
    """Request human approval for a medium or high risk action.
    
    If APPROVAL_API_URL is configured: Sends email via SNS with approve/reject links,
    then polls DynamoDB for the response (timeout: 5 minutes).
    
    If not configured: Falls back to interactive terminal prompt.
    
    Returns approval status: approved, rejected, or timeout.
    """
    import uuid
    import time as _time

    api_url = os.getenv('APPROVAL_API_URL', '')
    table_name = os.getenv('APPROVAL_TABLE_NAME', '')
    topic_arn = os.getenv('APPROVAL_SNS_TOPIC_ARN', '')

    # If external approval is configured, use SNS + DynamoDB
    if api_url and table_name and topic_arn:
        request_id = str(uuid.uuid4())[:8]
        token = str(uuid.uuid4())[:16]
        ttl = int(_time.time()) + 1800  # 30 min expiry

        # Write pending request to DynamoDB
        ddb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = ddb.Table(table_name)
        table.put_item(Item={
            'request_id': request_id,
            'status': 'pending',
            'action': action_name,
            'risk_level': risk_level,
            'description': description,
            'sql_statement': sql_statement,
            'token': token,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'ttl': ttl
        })

        # Send SNS notification with approve/reject links
        approve_url = f"{api_url}/approve?id={request_id}&token={token}"
        reject_url = f"{api_url}/reject?id={request_id}&token={token}"

        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        sql_section = f"\n  SQL STATEMENT:\n  {sql_statement}\n" if sql_statement else ""
        
        # Send HTML email via SES for beautiful buttons
        ses_sender = os.getenv('SES_SENDER_EMAIL', 'sudhamin@amazon.com')
        ses_recipient = os.getenv('SES_RECIPIENT_EMAIL', 'sudhamin@amazon.com')
        
        html_email = f"""
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f1f5f9; margin: 0; padding: 40px 20px;">
  <div style="max-width: 560px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); overflow: hidden;">
    
    <div style="background: linear-gradient(135deg, #1e293b 0%, #334155 100%); padding: 32px; text-align: center;">
      <h1 style="color: white; margin: 0; font-size: 20px; font-weight: 600;">Database Operations</h1>
      <p style="color: #94a3b8; margin: 8px 0 0; font-size: 14px;">Action Approval Request</p>
    </div>
    
    <div style="padding: 32px;">
      <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 24px;">
        <strong style="color: #92400e;">Risk Level: {risk_level}</strong>
      </div>
      
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px;">
        <tr>
          <td style="padding: 8px 0; color: #64748b; font-size: 14px; width: 120px;">Action</td>
          <td style="padding: 8px 0; color: #1e293b; font-size: 14px; font-weight: 600;">{action_name}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Request ID</td>
          <td style="padding: 8px 0; color: #1e293b; font-size: 14px; font-family: monospace;">{request_id}</td>
        </tr>
        <tr>
          <td style="padding: 8px 0; color: #64748b; font-size: 14px;">Timestamp</td>
          <td style="padding: 8px 0; color: #1e293b; font-size: 14px;">{timestamp_str}</td>
        </tr>
      </table>
      
      <div style="background: #f8fafc; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
        <p style="color: #64748b; font-size: 12px; text-transform: uppercase; margin: 0 0 8px; letter-spacing: 0.5px;">Description</p>
        <p style="color: #1e293b; font-size: 14px; margin: 0;">{description}</p>
      </div>
      
      {"<div style='background: #f8fafc; border-radius: 8px; padding: 16px; margin-bottom: 24px;'><p style=color: #64748b; font-size: 12px; text-transform: uppercase; margin: 0 0 8px; letter-spacing: 0.5px;>SQL Statement</p><pre style=color: #1e293b; font-size: 13px; margin: 0; white-space: pre-wrap;>" + sql_statement + "</pre></div>" if sql_statement else ""}
      
      <div style="text-align: center; padding: 24px 0;">
        <a href="{approve_url}" style="display: inline-block; background: #10b981; color: white; padding: 14px 36px; 
           border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 0 8px;
           box-shadow: 0 2px 8px rgba(16,185,129,0.3);">
          Approve
        </a>
        <a href="{reject_url}" style="display: inline-block; background: #ef4444; color: white; padding: 14px 36px; 
           border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px; margin: 0 8px;
           box-shadow: 0 2px 8px rgba(239,68,68,0.3);">
          Reject
        </a>
      </div>
      
      <p style="color: #94a3b8; font-size: 12px; text-align: center; margin: 16px 0 0;">
        This request expires in 30 minutes. If no action is taken, the request will be auto-rejected.
      </p>
    </div>
    
    <div style="background: #f8fafc; padding: 16px 32px; text-align: center; border-top: 1px solid #e2e8f0;">
      <p style="color: #94a3b8; font-size: 11px; margin: 0;">Autonomous DB Operations &bull; Actions Agent</p>
    </div>
  </div>
</body>
</html>"""

        # Try SES first (HTML), fall back to SNS (plain text)
        try:
            ses = boto3.client('ses', region_name=AWS_REGION)
            ses.send_email(
                Source=ses_sender,
                Destination={'ToAddresses': [ses_recipient]},
                Message={
                    'Subject': {'Data': f'[{risk_level}] Approve: {action_name}'},
                    'Body': {
                        'Html': {'Data': html_email},
                        'Text': {'Data': f'Action: {action_name}\nRisk: {risk_level}\nDescription: {description}\n\nApprove: {approve_url}\nReject: {reject_url}'}
                    }
                }
            )
        except Exception as ses_error:
            # Fallback to SNS plain text
            plain_text = f"Action: {action_name}\nRisk: {risk_level}\nRequest ID: {request_id}\n\nDescription: {description}\n{sql_section}\n\nAPPROVE: {approve_url}\n\nREJECT: {reject_url}\n\nExpires in 30 minutes."
            sns = boto3.client('sns', region_name=AWS_REGION)
            sns.publish(
                TopicArn=topic_arn,
                Subject=f'[{risk_level}] Approve: {action_name}',
                Message=plain_text
            )

        print(f"\n  📧 Approval request sent (ID: {request_id}). Waiting for response...")

        # Poll DynamoDB for response (timeout 5 minutes)
        timeout = 300
        start = _time.time()
        while _time.time() - start < timeout:
            item = table.get_item(Key={'request_id': request_id}).get('Item', {})
            status = item.get('status', 'pending')
            if status != 'pending':
                print(f"  {'✅' if status == 'approved' else '❌'} Response received: {status}")
                return {
                    'status': status,
                    'action': action_name,
                    'decided_by': 'human_operator_via_email',
                    'request_id': request_id,
                    'timestamp': item.get('decided_at', '')
                }
            _time.sleep(5)

        # Timeout
        print("  ⏰ Approval request timed out (5 minutes)")
        return {
            'status': 'timeout',
            'action': action_name,
            'message': 'No response received within 5 minutes. Action not executed.',
            'request_id': request_id
        }

    # Fallback: interactive terminal approval
    print("\n" + "=" * 60)
    print(f"🔒 APPROVAL REQUIRED - {risk_level} RISK ACTION")
    print("=" * 60)
    print(f"\n  Action: {action_name}")
    print(f"  Risk Level: {risk_level}")
    print(f"  Description: {description}")
    if sql_statement:
        print(f"\n  SQL Statement:")
        print(f"    {sql_statement}")
    print(f"\n" + "-" * 60)

    try:
        response = input("\n  Approve? (yes/no): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        response = 'no'

    if response in ('yes', 'y', 'approve'):
        return {
            'status': 'approved',
            'action': action_name,
            'approved_by': 'human_operator',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    else:
        return {
            'status': 'rejected',
            'action': action_name,
            'rejected_by': 'human_operator',
            'reason': response if response not in ('no', 'n', 'reject') else 'Operator declined',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


# ===== ACTION TOOLS =====

@tool
def create_index(create_index_statement: str, reason: str = "") -> Dict[str, Any]:
    """Create an index on the database. MEDIUM-RISK action requiring approval.
    
    Accepts a CREATE INDEX statement. Do NOT add WITH (ONLINE = ON) unless you know the instance is Enterprise Edition.
    
    Args:
        create_index_statement: The CREATE INDEX SQL statement
        reason: Why this index is needed (for audit trail)
    
    Example: CREATE NONCLUSTERED INDEX IX_Orders_ShippingState ON Orders(ShippingState) INCLUDE (OrderID, TotalAmount)
    """
    try:
        # Validate it's a CREATE INDEX statement
        stmt = create_index_statement.strip().upper()
        if not stmt.startswith('CREATE') or 'INDEX' not in stmt:
            return {'status': 'error', 'error': 'Only CREATE INDEX statements are allowed'}

        # Safety: reject dangerous operations
        dangerous = ['DROP ', 'DELETE ', 'TRUNCATE ', 'ALTER TABLE', 'INSERT ', 'UPDATE ']
        for d in dangerous:
            if d in stmt:
                return {'status': 'error', 'error': f'Dangerous operation detected: {d.strip()}. Rejected.'}

        # Note: ONLINE=ON requires Enterprise Edition. Do not auto-add.

        # Execute
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(create_index_statement)
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'create_index',
            'risk_level': 'MEDIUM',
            'statement_executed': create_index_statement,
            'reason': reason,
            'message': 'Index created successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'statement': create_index_statement}


@tool
def update_statistics(table_name: str) -> Dict[str, Any]:
    """Update statistics for a table to help the query optimizer. LOW-RISK action, auto-approved.
    
    Args:
        table_name: Name of the table to update statistics for
    """
    try:
        # Validate table name
        if not all(c.isalnum() or c == '_' for c in table_name):
            return {'status': 'error', 'error': 'Invalid table name. Use alphanumeric and underscore only.'}

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'UPDATE STATISTICS {table_name} WITH FULLSCAN')
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'update_statistics',
            'risk_level': 'LOW',
            'table': table_name,
            'message': f'Statistics updated for {table_name} with FULLSCAN',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def force_query_plan(query_id: int, plan_id: int, reason: str = "") -> Dict[str, Any]:
    """Force a specific execution plan for a query using Query Store. MEDIUM-RISK action.
    
    Forces the optimizer to use a specific plan. Use get_query_store_plan_summary 
    from the query performance agent first to identify the good plan_id.
    
    Args:
        query_id: Query Store query ID
        plan_id: The plan ID to force
        reason: Why this plan is being forced (for audit trail)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'EXEC sp_query_store_force_plan @query_id = {int(query_id)}, @plan_id = {int(plan_id)}')
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'force_query_plan',
            'risk_level': 'MEDIUM',
            'query_id': query_id,
            'plan_id': plan_id,
            'reason': reason,
            'message': f'Plan {plan_id} forced for query {query_id}.',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def unforce_query_plan(query_id: int, plan_id: int) -> Dict[str, Any]:
    """Unforce a previously forced plan. LOW-RISK action, auto-approved.
    Returns to normal optimizer behavior.
    
    Args:
        query_id: Query Store query ID
        plan_id: The plan ID to unforce
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'EXEC sp_query_store_unforce_plan @query_id = {int(query_id)}, @plan_id = {int(plan_id)}')
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'unforce_query_plan',
            'risk_level': 'LOW',
            'query_id': query_id,
            'plan_id': plan_id,
            'message': f'Plan {plan_id} unforced for query {query_id}. Optimizer will choose plan.',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ===== INDEX MAINTENANCE TOOLS =====

@tool
def check_stale_statistics(threshold_pct: float = 20.0) -> Dict[str, Any]:
    """Check for tables with stale statistics. 
    
    Returns tables where modification_counter exceeds threshold percentage of total rows.
    Stale stats cause the optimizer to make bad decisions (wrong join types, wrong access methods).
    
    Args:
        threshold_pct: Percentage of rows modified to consider stats stale (default 20%)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT 
                t.name AS TableName,
                s.name AS StatName,
                sp.last_updated,
                sp.rows AS total_rows,
                sp.modification_counter,
                CAST(sp.modification_counter * 100.0 / NULLIF(sp.rows, 0) AS DECIMAL(5,2)) AS pct_modified
            FROM sys.stats s
            INNER JOIN sys.tables t ON s.object_id = t.object_id
            CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
            WHERE sp.modification_counter > 0
            AND sp.rows > 0
            AND CAST(sp.modification_counter * 100.0 / sp.rows AS DECIMAL(5,2)) >= {threshold_pct}
            ORDER BY sp.modification_counter DESC
        """)

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return {
            'stale_statistics': results,
            'count': len(results),
            'threshold_pct': threshold_pct,
            'recommendation': 'Run update_statistics on affected tables' if results else 'All statistics are fresh'
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ===== INDEX MAINTENANCE TOOLS =====

@tool
def check_index_fragmentation(table_name: str = None) -> Dict[str, Any]:
    """Check index fragmentation levels. Returns indexes needing maintenance.
    
    Thresholds:
    - 10-30% fragmentation → REORGANIZE (online, non-blocking)
    - >30% fragmentation → REBUILD
    
    Args:
        table_name: Optional - check specific table. If None, checks all tables.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        where_clause = f"AND t.name = '{table_name}'" if table_name else ""

        cursor.execute(f"""
            SELECT 
                t.name AS TableName,
                i.name AS IndexName,
                ips.avg_fragmentation_in_percent,
                ips.page_count,
                ips.index_type_desc,
                CASE 
                    WHEN ips.avg_fragmentation_in_percent > 30 THEN 'REBUILD'
                    WHEN ips.avg_fragmentation_in_percent > 10 THEN 'REORGANIZE'
                    ELSE 'OK'
                END AS recommended_action
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
            INNER JOIN sys.tables t ON ips.object_id = t.object_id
            INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE ips.avg_fragmentation_in_percent > 10
            AND ips.page_count > 100
            AND i.name IS NOT NULL
            {where_clause}
            ORDER BY ips.avg_fragmentation_in_percent DESC
        """)

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        return {
            'fragmented_indexes': results,
            'count': len(results),
            'summary': {
                'need_reorganize': len([r for r in results if r['recommended_action'] == 'REORGANIZE']),
                'need_rebuild': len([r for r in results if r['recommended_action'] == 'REBUILD'])
            }
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def reorganize_index(table_name: str, index_name: str) -> Dict[str, Any]:
    """Reorganize a fragmented index. LOW-RISK action, auto-approved.
    
    REORGANIZE is always online and non-blocking. Safe to run anytime.
    Recommended for 10-30% fragmentation.
    
    Args:
        table_name: Table the index belongs to
        index_name: Name of the index to reorganize
    """
    try:
        # Validate names
        for name in [table_name, index_name]:
            if not all(c.isalnum() or c == '_' for c in name):
                return {'status': 'error', 'error': f'Invalid name: {name}'}

        conn = get_db_connection()
        cursor = conn.cursor()
        
        stmt = f'ALTER INDEX {index_name} ON {table_name} REORGANIZE'
        cursor.execute(stmt)
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'reorganize_index',
            'risk_level': 'LOW',
            'table': table_name,
            'index': index_name,
            'statement_executed': stmt,
            'message': f'Index {index_name} on {table_name} reorganized successfully (online, non-blocking)',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def rebuild_index(table_name: str, index_name: str) -> Dict[str, Any]:
    """Rebuild a heavily fragmented index. MEDIUM-RISK action, requires approval.
    
    Recommended for >30% fragmentation.
    More thorough than REORGANIZE but heavier operation.
    
    Args:
        table_name: Table the index belongs to
        index_name: Name of the index to rebuild
    """
    try:
        # Validate names
        for name in [table_name, index_name]:
            if not all(c.isalnum() or c == '_' for c in name):
                return {'status': 'error', 'error': f'Invalid name: {name}'}

        conn = get_db_connection()
        cursor = conn.cursor()
        
        stmt = f'ALTER INDEX {index_name} ON {table_name} REBUILD'
        cursor.execute(stmt)
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'rebuild_index',
            'risk_level': 'MEDIUM',
            'table': table_name,
            'index': index_name,
            'statement_executed': stmt,
            'message': f'Index {index_name} on {table_name} rebuilt successfully',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ===== STORED PROCEDURE FIX =====

@tool
def apply_procedure_fix(fix_sql: str, reason: str = "") -> Dict[str, Any]:
    """Apply an optimized stored procedure to the database. MEDIUM-RISK action requiring approval.

    Accepts a CREATE OR ALTER PROCEDURE statement that replaces an existing stored procedure
    with an optimized version. The LLM generates the fix based on its diagnosis.

    IMPORTANT: Only CREATE OR ALTER PROCEDURE statements are allowed. All other SQL is rejected.

    Args:
        fix_sql: The full CREATE OR ALTER PROCEDURE statement
        reason: Why this fix is being applied (for audit trail)

    Example: CREATE OR ALTER PROCEDURE dbo.sp_MonthlyOrderReport AS BEGIN ... END
    """
    try:
        stmt = fix_sql.strip().upper()

        if not (stmt.startswith('CREATE OR ALTER PROCEDURE') or
                stmt.startswith('CREATE PROCEDURE') or
                stmt.startswith('ALTER PROCEDURE')):
            return {'status': 'error', 'error': 'Only CREATE/ALTER PROCEDURE statements are allowed'}

        dangerous = ['DROP ', 'DELETE ', 'TRUNCATE ', 'INSERT ', 'UPDATE ', 'xp_cmdshell', 'SHUTDOWN']
        for d in dangerous:
            if d in stmt and 'UPDATE STATISTICS' not in stmt:
                return {'status': 'error', 'error': f'Dangerous operation detected: {d.strip()}. Rejected.'}

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(fix_sql)

        proc_name = fix_sql.split('PROCEDURE')[1].strip().split()[0].strip()

        cursor.execute(f"EXEC sp_recompile '{proc_name}'")
        conn.commit()
        cursor.close()
        conn.close()

        return {
            'status': 'success',
            'action': 'apply_procedure_fix',
            'risk_level': 'MEDIUM',
            'procedure': proc_name,
            'reason': reason,
            'statement_executed': fix_sql,
            'message': f'{proc_name} replaced with optimized version',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


# ===== CLOUDWATCH ALARM TOOLS =====

@tool
def get_alarm_status() -> Dict[str, Any]:
    """Check current state of the database CPU alarm.
    Returns: OK, ALARM, or INSUFFICIENT_DATA with last state change time.
    """
    try:
        cw_client = boto3.client('cloudwatch', region_name=AWS_REGION)
        response = cw_client.describe_alarms(
            AlarmNames=[f'{DB_INSTANCE_ID}-cpu-alarm']
        )

        if not response['MetricAlarms']:
            return {'status': 'error', 'error': 'No CPU alarm found'}

        alarm = response['MetricAlarms'][0]
        return {
            'alarm_name': alarm['AlarmName'],
            'state': alarm['StateValue'],
            'reason': alarm['StateReason'],
            'threshold': alarm['Threshold'],
            'metric': alarm['MetricName'],
            'last_updated': alarm['StateUpdatedTimestamp'].isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def get_alarm_history(hours_back: int = 24) -> Dict[str, Any]:
    """Get alarm state change history. Shows when alarm triggered and cleared.
    
    Args:
        hours_back: How many hours of history to retrieve (default 24)
    """
    try:
        cw_client = boto3.client('cloudwatch', region_name=AWS_REGION)
        
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        response = cw_client.describe_alarm_history(
            AlarmName=f'{DB_INSTANCE_ID}-cpu-alarm',
            HistoryItemType='StateUpdate',
            StartDate=start_time,
            EndDate=datetime.now(timezone.utc),
            MaxRecords=20
        )

        history = []
        for item in response.get('AlarmHistoryItems', []):
            history.append({
                'timestamp': item['Timestamp'].isoformat(),
                'summary': item['HistorySummary'],
                'type': item['HistoryItemType']
            })

        return {
            'alarm_name': f'{DB_INSTANCE_ID}-cpu-alarm',
            'history': history,
            'count': len(history)
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def acknowledge_alarm(notes: str = "") -> Dict[str, Any]:
    """Acknowledge that the alarm is being investigated.
    Logs the acknowledgment with timestamp for audit trail.
    Does NOT silence the alarm — just records that an operator/agent is working on it.
    
    Args:
        notes: Optional notes about what actions are being taken
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    acknowledgment = {
        'status': 'acknowledged',
        'alarm_name': f'{DB_INSTANCE_ID}-cpu-alarm',
        'acknowledged_at': timestamp,
        'acknowledged_by': 'actions_agent',
        'notes': notes or 'Alarm acknowledged. Investigation in progress.'
    }
    
    # Log to CloudWatch as annotation
    try:
        cw_client = boto3.client('cloudwatch', region_name=AWS_REGION)
        cw_client.set_alarm_state(
            AlarmName=f'{DB_INSTANCE_ID}-cpu-alarm',
            StateValue='OK',
            StateReason=f'Acknowledged by Actions Agent at {timestamp}. {notes}'
        )
        acknowledgment['alarm_reset'] = True
        acknowledgment['message'] = 'Alarm acknowledged and state reset to OK'
    except Exception as e:
        acknowledgment['alarm_reset'] = False
        acknowledgment['message'] = f'Acknowledged but could not reset alarm state: {e}'

    return acknowledgment


# ===== SNS NOTIFICATION TOOL =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS for action audit trail. Severity: INFO, WARNING, CRITICAL"""
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
SQL SERVER ACTIONS AGENT - ACTION EXECUTED
============================================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by Actions Agent (Autonomous DB Operations)
"""

        sns_subject = f"[{severity}] DB Action: {subject}"[:100]
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

system_prompt = """You are the Actions Agent. You execute exactly ONE database optimization action.

RULES:
1. Execute ONLY the single action requested. Nothing more. Do not add extra indexes or stats updates.
2. DO NOT GUESS. Only act on what was explicitly requested.
3. Workflow:
   a. Classify risk level
   b. If MEDIUM: request human approval, wait for response
   c. If approved (or LOW risk): execute
   d. Return the result
4. Do NOT diagnose or analyze. You only execute.
5. Do NOT use DROP statements.
6. Do NOT use WITH (ONLINE = ON) — Standard Edition.
7. If approval is rejected, STOP and report back.
8. If action fails, report the error. Do not retry or try alternatives.

Risk levels:
- LOW (auto-approve): update_statistics, unforce_query_plan, reorganize_index
- MEDIUM (needs approval): create_index, force_query_plan, rebuild_index

Tools:
- classify_action_risk
- request_human_approval
- create_index (MEDIUM)
- update_statistics (LOW)
- check_stale_statistics (read-only)
- force_query_plan (MEDIUM)
- unforce_query_plan (LOW)
- check_index_fragmentation (read-only)
- reorganize_index (LOW)
- rebuild_index (MEDIUM)
- get_alarm_status (read-only)
- get_alarm_history (read-only)
- send_email_notification
"""

agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        classify_action_risk,
        request_human_approval,
        create_index,
        update_statistics,
        check_stale_statistics,
        force_query_plan,
        unforce_query_plan,
        check_index_fragmentation,
        reorganize_index,
        rebuild_index,
        get_alarm_status,
        get_alarm_history,
        send_email_notification
    ]
)

if __name__ == "__main__":
    print("Actions Agent - Execute database optimizations with safety guardrails.")
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
