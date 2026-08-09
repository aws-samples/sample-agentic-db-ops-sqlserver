# Updated: 2026-03-15.
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

# Configuration from environment variables
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')

# Helper functions
def get_pi_client():
    """Get Performance Insights client"""
    return boto3.client('pi', region_name=AWS_REGION)

def get_rds_resource_id():
    """Get RDS resource ID dynamically"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        return db_response['DBInstances'][0]['DbiResourceId']
    except Exception as e:
        raise Exception(f"Error getting RDS resource ID: {str(e)}")

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
            database='master'
        )
        return conn
    except Exception as e:
        print(f"DEBUG - Connection error: {type(e).__name__}: {str(e)}")
        raise Exception(f"Error connecting to database: {str(e)}")

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.0
)

# ===== QUERY STORE TOOLS =====

@tool
def check_query_store_enabled() -> Dict[str, Any]:
    """Check if Query Store is enabled and get configuration"""
    try:
        print("DEBUG: Attempting to connect to database...")
        conn = get_db_connection()
        print("DEBUG: Connection successful, executing query...")
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                actual_state_desc,
                readonly_reason,
                desired_state_desc,
                current_storage_size_mb,
                max_storage_size_mb,
                query_capture_mode_desc
            FROM sys.database_query_store_options
        """)
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            return {
                'enabled': row[0] in ('READ_WRITE', 'READ_ONLY'),
                'state': row[0],
                'readonly_reason': row[1],
                'desired_state': row[2],
                'storage_used_mb': row[3],
                'storage_max_mb': row[4],
                'capture_mode': row[5]
            }
        return {'enabled': False, 'error': 'Query Store not configured'}
    except Exception as e:
        print(f"DEBUG: Exception caught: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'enabled': False, 'error': str(e)}

@tool
def get_query_store_top_queries(hours_back: int = 24, top_n: int = 10, metric: str = "cpu") -> Dict[str, Any]:
    """Get top resource-consuming queries from Query Store. Metric: cpu, duration, io, memory"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        order_by = {
            "cpu": "qrs.avg_cpu_time DESC",
            "duration": "qrs.avg_duration DESC",
            "io": "qrs.avg_logical_io_reads DESC",
            "memory": "qrs.avg_query_max_used_memory DESC"
        }.get(metric, "qrs.avg_cpu_time DESC")
        
        query = f"""
        SELECT TOP {top_n}
            qsq.query_id,
            SUBSTRING(CAST(qst.query_sql_text AS NVARCHAR(MAX)), 1, 500) as query_text,
            qrs.avg_cpu_time / 1000 as avg_cpu_ms,
            qrs.avg_duration / 1000 as avg_duration_ms,
            qrs.avg_logical_io_reads,
            qrs.avg_query_max_used_memory * 8 / 1024 as avg_memory_mb,
            qrs.count_executions,
            qrs.last_execution_time
        FROM sys.query_store_query qsq
        JOIN sys.query_store_query_text qst ON qsq.query_text_id = qst.query_text_id
        JOIN sys.query_store_plan qp ON qsq.query_id = qp.query_id
        JOIN sys.query_store_runtime_stats qrs ON qp.plan_id = qrs.plan_id
        JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
        WHERE qrsi.start_time >= DATEADD(hour, -{hours_back}, GETUTCDATE())
        ORDER BY {order_by}
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_query_store_regressed_queries(hours_back: int = 24) -> Dict[str, Any]:
    """Detect queries that regressed in performance (comparing recent vs historical)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
        WITH recent_stats AS (
            SELECT qp.query_id, AVG(qrs.avg_cpu_time) as recent_cpu, AVG(qrs.avg_duration) as recent_duration
            FROM sys.query_store_runtime_stats qrs
            JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
            JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
            WHERE qrsi.start_time >= DATEADD(hour, -{hours_back}, GETUTCDATE())
            GROUP BY qp.query_id
        ),
        historical_stats AS (
            SELECT qp.query_id, AVG(qrs.avg_cpu_time) as hist_cpu, AVG(qrs.avg_duration) as hist_duration
            FROM sys.query_store_runtime_stats qrs
            JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
            JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
            WHERE qrsi.start_time < DATEADD(hour, -{hours_back}, GETUTCDATE())
            GROUP BY qp.query_id
        )
        SELECT TOP 10
            q.query_id,
            SUBSTRING(CAST(qt.query_sql_text AS NVARCHAR(MAX)), 1, 500) as query_text,
            rs.recent_cpu / 1000 as recent_cpu_ms,
            hs.hist_cpu / 1000 as historical_cpu_ms,
            CAST((rs.recent_cpu - hs.hist_cpu) / hs.hist_cpu * 100 AS DECIMAL(10,2)) as cpu_regression_pct,
            rs.recent_duration / 1000 as recent_duration_ms,
            hs.hist_duration / 1000 as historical_duration_ms
        FROM recent_stats rs
        JOIN historical_stats hs ON rs.query_id = hs.query_id
        JOIN sys.query_store_query q ON rs.query_id = q.query_id
        JOIN sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
        WHERE rs.recent_cpu > hs.hist_cpu * 1.5
        ORDER BY cpu_regression_pct DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'regressed_queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_query_store_wait_stats(query_id: int = None, hours_back: int = 24) -> Dict[str, Any]:
    """Get wait statistics from Query Store for specific query or all queries"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        where_clause = f"AND qp.query_id = {query_id}" if query_id else ""
        
        query = f"""
        SELECT TOP 20
            qp.query_id,
            qsws.wait_category_desc,
            qsws.avg_query_wait_time_ms,
            qsws.total_query_wait_time_ms,
            qsws.execution_type_desc
        FROM sys.query_store_wait_stats qsws
        JOIN sys.query_store_plan qp ON qsws.plan_id = qp.plan_id
        JOIN sys.query_store_runtime_stats_interval qrsi ON qsws.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
        WHERE qrsi.start_time >= DATEADD(hour, -{hours_back}, GETUTCDATE())
        {where_clause}
        ORDER BY qsws.avg_query_wait_time_ms DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'wait_stats': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_query_execution_history(query_id: int, hours_back: int = 168) -> Dict[str, Any]:
    """Get execution history timeline for a specific query (up to 7 days)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
        SELECT 
            qrsi.start_time,
            qrsi.end_time,
            qrs.count_executions,
            qrs.avg_cpu_time / 1000 as avg_cpu_ms,
            qrs.avg_duration / 1000 as avg_duration_ms,
            qrs.avg_logical_io_reads,
            qrs.avg_query_max_used_memory * 8 / 1024 as avg_memory_mb
        FROM sys.query_store_runtime_stats qrs
        JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
        JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
        WHERE qp.query_id = {query_id}
        AND qrsi.start_time >= DATEADD(hour, -{hours_back}, GETUTCDATE())
        ORDER BY qrsi.start_time
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'timeline': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_query_store_plan_summary(query_id: int) -> Dict[str, Any]:
    """Get execution plan summary for a specific query"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
        SELECT 
            qp.plan_id,
            qp.is_forced_plan,
            qrs.avg_cpu_time / 1000 as avg_cpu_ms,
            qrs.avg_duration / 1000 as avg_duration_ms,
            qrs.count_executions,
            qrs.first_execution_time,
            qrs.last_execution_time
        FROM sys.query_store_plan qp
        JOIN sys.query_store_runtime_stats qrs ON qp.plan_id = qrs.plan_id
        WHERE qp.query_id = {query_id}
        ORDER BY qrs.avg_cpu_time DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'plans': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

# ===== DMV TOOLS =====

@tool
def get_slow_queries(threshold_seconds: int = 5) -> Dict[str, Any]:
    """Get currently running slow queries from sys.dm_exec_requests"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
        SELECT TOP 10
            r.session_id,
            r.status,
            r.command,
            r.cpu_time,
            r.total_elapsed_time / 1000 as elapsed_seconds,
            r.logical_reads,
            r.writes,
            r.blocking_session_id,
            SUBSTRING(st.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(st.text)
                    ELSE r.statement_end_offset
                END - r.statement_start_offset)/2) + 1) AS query_text
        FROM sys.dm_exec_requests r
        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
        WHERE r.session_id > 50
        AND r.total_elapsed_time / 1000 > {threshold_seconds}
        ORDER BY r.total_elapsed_time DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'slow_queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_blocking_sessions() -> Dict[str, Any]:
    """Get blocking sessions and what they're blocking"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            blocking.session_id AS blocking_session_id,
            blocked.session_id AS blocked_session_id,
            blocking_text.text AS blocking_query,
            blocked_text.text AS blocked_query,
            blocked.wait_time / 1000 AS wait_seconds,
            blocked.wait_type
        FROM sys.dm_exec_requests blocked
        INNER JOIN sys.dm_exec_requests blocking
            ON blocked.blocking_session_id = blocking.session_id
        CROSS APPLY sys.dm_exec_sql_text(blocking.sql_handle) blocking_text
        CROSS APPLY sys.dm_exec_sql_text(blocked.sql_handle) blocked_text
        WHERE blocked.blocking_session_id > 0
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'blocking_sessions': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_query_plan_from_cache(query_fragment: str) -> Dict[str, Any]:
    """Get execution plan from plan cache for queries matching the fragment"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Escape single quotes in the fragment
        safe_fragment = query_fragment.replace("'", "''")
        
        query = f"""
        SELECT TOP 5
            SUBSTRING(st.text, 1, 500) as query_text,
            qs.execution_count,
            qs.total_worker_time / 1000 as total_cpu_ms,
            qs.total_elapsed_time / 1000 as total_duration_ms,
            qs.total_logical_reads,
            qs.total_logical_writes,
            CAST(qp.query_plan AS NVARCHAR(MAX)) as execution_plan_xml
        FROM sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
        CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
        WHERE st.text LIKE '%{safe_fragment}%'
        ORDER BY qs.total_worker_time DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            # Truncate plan XML for readability
            if result.get('execution_plan_xml'):
                result['execution_plan_xml'] = result['execution_plan_xml'][:1000] + '...(truncated)'
            results.append(result)
        
        cursor.close()
        conn.close()
        
        return {'plans': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_expensive_queries_from_cache(top_n: int = 10, metric: str = "cpu") -> Dict[str, Any]:
    """Get top expensive queries from plan cache (since last restart). Metric: cpu, duration, reads, writes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        order_by = {
            "cpu": "qs.total_worker_time DESC",
            "duration": "qs.total_elapsed_time DESC",
            "reads": "qs.total_logical_reads DESC",
            "writes": "qs.total_logical_writes DESC"
        }.get(metric, "qs.total_worker_time DESC")
        
        query = f"""
        SELECT TOP {top_n}
            SUBSTRING(st.text, 1, 500) as query_text,
            qs.execution_count,
            qs.total_worker_time / 1000 as total_cpu_ms,
            qs.total_elapsed_time / 1000 as total_duration_ms,
            qs.total_logical_reads,
            qs.total_logical_writes,
            qs.creation_time,
            qs.last_execution_time
        FROM sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
        ORDER BY {order_by}
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def suggest_indexes(table_name: str = None) -> Dict[str, Any]:
    """Get missing index recommendations from DMVs with CREATE INDEX statements"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        where_clause = f"AND OBJECT_NAME(d.object_id, d.database_id) = '{table_name}'" if table_name else ""
        
        query = f"""
        SELECT TOP 10
            OBJECT_NAME(d.object_id, d.database_id) AS table_name,
            d.equality_columns,
            d.inequality_columns,
            d.included_columns,
            s.avg_total_user_cost * s.avg_user_impact * (s.user_seeks + s.user_scans) AS improvement_measure,
            'CREATE INDEX IX_' + OBJECT_NAME(d.object_id, d.database_id) + '_' + 
                REPLACE(REPLACE(REPLACE(ISNULL(d.equality_columns, ''), ', ', '_'), '[', ''), ']', '') +
                CASE WHEN d.inequality_columns IS NOT NULL THEN '_' + 
                    REPLACE(REPLACE(REPLACE(d.inequality_columns, ', ', '_'), '[', ''), ']', '') 
                ELSE '' END +
            ' ON ' + d.statement + ' (' + 
                ISNULL(d.equality_columns, '') +
                CASE WHEN d.equality_columns IS NOT NULL AND d.inequality_columns IS NOT NULL THEN ', ' ELSE '' END +
                ISNULL(d.inequality_columns, '') + ')' +
                CASE WHEN d.included_columns IS NOT NULL THEN ' INCLUDE (' + d.included_columns + ')' ELSE '' END 
            AS create_index_statement,
            s.user_seeks,
            s.user_scans,
            s.last_user_seek,
            s.last_user_scan
        FROM sys.dm_db_missing_index_details d
        INNER JOIN sys.dm_db_missing_index_groups g ON d.index_handle = g.index_handle
        INNER JOIN sys.dm_db_missing_index_group_stats s ON g.index_group_handle = s.group_handle
        WHERE d.database_id = DB_ID()
        {where_clause}
        ORDER BY improvement_measure DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'missing_indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_index_usage() -> Dict[str, Any]:
    """Get index usage statistics to identify unused indexes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 20
            OBJECT_NAME(s.object_id) AS table_name,
            i.name AS index_name,
            s.user_seeks,
            s.user_scans,
            s.user_lookups,
            s.user_updates,
            CASE 
                WHEN s.user_seeks + s.user_scans + s.user_lookups = 0 THEN 'UNUSED'
                WHEN s.user_updates > (s.user_seeks + s.user_scans + s.user_lookups) * 10 THEN 'EXPENSIVE'
                ELSE 'USED'
            END AS usage_status
        FROM sys.dm_db_index_usage_stats s
        INNER JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
        WHERE s.database_id = DB_ID()
        AND OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
        ORDER BY s.user_updates DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'index_usage': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

# ===== SNS NOTIFICATION TOOL =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    try:
        region = os.getenv('AWS_REGION', 'us-west-2')
        topic_name = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
        
        sns_client = boto3.client('sns', region_name=region)
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
SQL SERVER QUERY PERFORMANCE ALERT
===================================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by AgentCore Query Performance Agent
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

system_prompt = """You are a TOOL EXECUTOR for RDS SQL Server query performance (Query Store + DMVs).

Your ONLY job is to call the right tools and return their raw output. You are not a reasoner.

RULES:
1. Call the tools relevant to the request and return their raw results verbatim.
2. Do NOT rank ("top problematic"), classify, summarize, interpret, or diagnose. No prose, no conclusions.
3. Do NOT provide action items or fix suggestions.
4. Do NOT send email notifications.
5. ROUTING (this is the one decision you make — tool selection, not interpretation):
   call check_query_store_enabled first. If enabled, use Query Store tools; if disabled,
   use DMV tools and include a flag noting Query Store is unavailable.
6. If a tool returns no data or an error, return that fact as-is. Never invent values.

The Supervisor does ALL reasoning. You only execute tools and hand back data.

Tools:

Query Store (if enabled):
- check_query_store_enabled: Check availability
- get_query_store_top_queries: Top queries by cpu/duration/io/memory
- get_query_store_regressed_queries: Performance regressions
- get_query_store_wait_stats: Wait stats per query
- get_query_execution_history: Performance timeline
- get_query_store_plan_summary: Execution plans

DMVs (always available):
- get_slow_queries: Currently running slow queries
- get_blocking_sessions: Blocking chains
- get_query_plan_from_cache: Execution plans
- get_expensive_queries_from_cache: Top queries since restart
- suggest_indexes: Missing index recommendations
- get_index_usage_stats: Index usage

Workflow:
1. Call check_query_store_enabled first
2. If enabled: use Query Store tools
3. If disabled: use DMV tools, include a flag that Query Store is unavailable
4. Return the raw tool outputs

Return the raw tool results (query store status + query metrics + index/blocking data). Do not rank or format into a report — the Supervisor interprets the data."""

agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        check_query_store_enabled,
        get_query_store_top_queries,
        get_query_store_regressed_queries,
        get_query_store_wait_stats,
        get_query_execution_history,
        get_query_store_plan_summary,
        get_slow_queries,
        get_blocking_sessions,
        get_query_plan_from_cache,
        get_expensive_queries_from_cache,
        suggest_indexes,
        get_index_usage,
        send_email_notification
    ]
)

if __name__ == "__main__":
    print("Query Performance Agent - Analyze and optimize SQL Server query performance.")
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

