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
# Must be the workload database, NOT master. Query Store options
# (sys.database_query_store_options) and the missing-index / index-usage DMVs are
# scoped by DB_ID(), so connecting to master makes them silently return no rows.
DB_NAME = os.getenv('DB_NAME', 'TravelHub')

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
            database=DB_NAME,
            # Without these, a diagnostic query that queues on RESOURCE_SEMAPHORE
            # hangs the agent indefinitely with no feedback. Fail fast instead so the
            # Supervisor can report a data gap.
            login_timeout=int(os.getenv('DB_LOGIN_TIMEOUT', '15')),
            timeout=int(os.getenv('DB_QUERY_TIMEOUT', '60')),
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
    """Get missing index recommendations from DMVs with CREATE INDEX statements.

    CORROBORATING EVIDENCE ONLY. sys.dm_db_missing_index_details is advisory: it is only
    populated when the optimizer happened to note a usable index at compile time, it is
    unaware of existing indexes, and it records nothing when the real problem is join
    cardinality. An empty result does NOT mean indexing would not help.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # No ORDER BY: a Sort operator requires a memory grant, which makes this tool
        # queue behind the workload on a RESOURCE_SEMAPHORE-starved instance. Sort in Python.
        query = """
        SELECT
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
          AND (%s IS NULL OR OBJECT_NAME(d.object_id, d.database_id) = %s)
        """

        cursor.execute(query, (table_name, table_name))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        results.sort(key=lambda r: float(r.get('improvement_measure') or 0), reverse=True)
        results = results[:10]

        return {
            'missing_indexes': results,
            'count': len(results),
            'caveat': ('Advisory DMV data. Empty result means the optimizer logged no '
                       'recommendation, NOT that indexing cannot help. Confirm against the '
                       'execution plan before acting.')
        }
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

# ===== TRIAGE TOOLS (Phase 1: what is running and what is it waiting on) =====

def _fetch(cursor) -> list:
    """Turn a cursor's result set into a list of dicts keyed by column name."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


_SHOWPLAN_NS = '{http://schemas.microsoft.com/sqlserver/2004/07/showplan}'
# Warning elements that directly indicate a code-level problem rather than a missing index.
_PLAN_WARNING_TAGS = (
    'PlanAffectingConvert',      # implicit conversion -> non-SARGable predicate
    'SpillToTempDb',             # undersized memory grant
    'ColumnsWithNoStatistics',   # cardinality estimate has no basis
    'NoJoinPredicate',           # cartesian product
    'UnmatchedIndexes',          # filtered index could not be used (parameterisation)
    'MemoryGrantWarning',
)


def _summarize_showplan(plan_xml: str, max_operators: int = 40) -> Dict[str, Any]:
    """Reduce showplan XML to the facts needed for root cause.

    Returns per-operator estimated vs actual row counts, plan warnings and memory grant
    detail. Returning the raw XML would be tens of thousands of tokens; the estimate/actual
    skew and the warning list are what actually identify the mechanism.
    """
    import xml.etree.ElementTree as ET

    ns = _SHOWPLAN_NS
    out = {'operators': [], 'top_row_estimate_skew': [], 'plan_warnings': [],
           'memory_grant': {}, 'operator_count': 0, 'truncated': False, 'parse_error': None}
    try:
        root = ET.fromstring(plan_xml)
    except Exception as e:
        out['parse_error'] = f'{type(e).__name__}: {e}'
        return out

    parents = {child: parent for parent in root.iter() for child in parent}

    def nearest_relop(el):
        p = parents.get(el)
        while p is not None:
            if p.tag == f'{ns}RelOp':
                return p
            p = parents.get(p)
        return None

    mg = root.find(f'.//{ns}MemoryGrantInfo')
    if mg is not None:
        out['memory_grant'] = dict(mg.attrib)
    qp = root.find(f'.//{ns}QueryPlan')
    if qp is not None:
        for k in ('DegreeOfParallelism', 'MemoryGrant', 'CachedPlanSize',
                  'CompileTime', 'CompileCPU', 'CompileMemory'):
            if k in qp.attrib:
                out['memory_grant'].setdefault(k, qp.attrib[k])

    for el in root.iter():
        tag = el.tag.replace(ns, '')
        if tag in _PLAN_WARNING_TAGS:
            entry = {'type': tag}
            entry.update({k: v for k, v in el.attrib.items()})
            owner = nearest_relop(el)
            if owner is not None:
                entry['node_id'] = owner.attrib.get('NodeId')
            out['plan_warnings'].append(entry)

    # Map each accessed object to the operator that owns it.
    objects_by_relop = {}
    for obj in root.iter(f'{ns}Object'):
        owner = nearest_relop(obj)
        if owner is None:
            continue
        desc = {k: obj.attrib[k] for k in ('Table', 'Index', 'IndexKind') if obj.attrib.get(k)}
        if desc:
            objects_by_relop.setdefault(id(owner), []).append(desc)

    relops = list(root.iter(f'{ns}RelOp'))
    out['operator_count'] = len(relops)

    for op in relops:
        a = op.attrib
        est = float(a.get('EstimateRows') or 0)
        actual_rows = 0.0
        actual_exec = 0.0
        has_actual = False
        rti = op.find(f'{ns}RunTimeInformation')
        if rti is not None:
            for t in rti.findall(f'{ns}RunTimeCountersPerThread'):
                has_actual = True
                actual_rows += float(t.attrib.get('ActualRows') or 0)
                actual_exec += float(t.attrib.get('ActualExecutions') or 0)

        entry = {
            'node_id': a.get('NodeId'),
            'physical_op': a.get('PhysicalOp'),
            'logical_op': a.get('LogicalOp'),
            'estimate_rows': est,
            'actual_rows': actual_rows if has_actual else None,
            'actual_executions': actual_exec if has_actual else None,
            'estimated_subtree_cost': a.get('EstimatedTotalSubtreeCost'),
            'objects': objects_by_relop.get(id(op), [])[:3],
        }
        if has_actual and est > 0:
            entry['actual_vs_estimate_ratio'] = round(actual_rows / est, 2)
        out['operators'].append(entry)

    if len(out['operators']) > max_operators:
        out['operators'] = out['operators'][:max_operators]
        out['truncated'] = True

    skewed = [o for o in out['operators'] if o.get('actual_vs_estimate_ratio')]
    skewed.sort(key=lambda o: o['actual_vs_estimate_ratio'], reverse=True)
    out['top_row_estimate_skew'] = skewed[:5]

    return out


@tool
def get_active_requests(min_elapsed_seconds: int = 0) -> Dict[str, Any]:
    """List every active user request with its wait type, memory grant and blocking info.

    This is the Phase 1 triage tool. Returns session_id and plan_handle for each request so
    a specific session can be drilled into with get_live_execution_plan.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # No ORDER BY (avoids a Sort memory grant on a starved instance) - sorted in Python.
        query = """
        SELECT
            r.session_id,
            r.status,
            r.command,
            r.wait_type,
            r.last_wait_type,
            r.wait_time AS wait_time_ms,
            r.wait_resource,
            r.blocking_session_id,
            r.cpu_time AS cpu_time_ms,
            r.total_elapsed_time / 1000 AS elapsed_seconds,
            r.logical_reads,
            r.writes,
            r.granted_query_memory * 8 / 1024.0 AS granted_memory_mb,
            r.dop,
            r.open_transaction_count,
            DB_NAME(r.database_id) AS database_name,
            s.login_name,
            s.program_name,
            s.host_name,
            CONVERT(VARCHAR(128), r.plan_handle, 1) AS plan_handle,
            CONVERT(VARCHAR(34), r.query_hash, 1) AS query_hash,
            SUBSTRING(t.text, (r.statement_start_offset / 2) + 1,
                ((CASE r.statement_end_offset WHEN -1 THEN DATALENGTH(t.text)
                  ELSE r.statement_end_offset END - r.statement_start_offset) / 2) + 1
            ) AS statement_text
        FROM sys.dm_exec_requests r
        INNER JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.session_id <> @@SPID
          AND s.is_user_process = 1
          AND r.total_elapsed_time / 1000 >= %s
        """

        cursor.execute(query, (min_elapsed_seconds,))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        results.sort(key=lambda r: (r.get('elapsed_seconds') or 0), reverse=True)

        waits = {}
        for r in results:
            w = r.get('wait_type') or 'RUNNING (no wait)'
            waits[w] = waits.get(w, 0) + 1

        return {
            'active_requests': results,
            'count': len(results),
            'wait_type_counts': waits,
        }
    except Exception as e:
        return {'error': str(e)}


@tool
def get_memory_grants() -> Dict[str, Any]:
    """Get memory grant queue state and per-query grants.

    Use when RESOURCE_SEMAPHORE appears in wait analysis. waiter_count > 0 on a semaphore
    means queries are queued waiting for workspace memory; grant_time IS NULL on a grant
    means that query is still waiting. This is the definitive tool for grant starvation.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            resource_semaphore_id,
            pool_id,
            target_memory_kb / 1024 AS target_memory_mb,
            available_memory_kb / 1024 AS available_memory_mb,
            granted_memory_kb / 1024 AS granted_memory_mb,
            used_memory_kb / 1024 AS used_memory_mb,
            grantee_count,
            waiter_count,
            timeout_error_count,
            forced_grant_count
        FROM sys.dm_exec_query_resource_semaphores
        """)
        cols = [d[0] for d in cursor.description]
        semaphores = [dict(zip(cols, row)) for row in cursor.fetchall()]

        cursor.execute("""
        SELECT
            g.session_id,
            g.request_time,
            g.grant_time,
            g.requested_memory_kb / 1024.0 AS requested_memory_mb,
            g.granted_memory_kb / 1024.0 AS granted_memory_mb,
            g.required_memory_kb / 1024.0 AS required_memory_mb,
            g.used_memory_kb / 1024.0 AS used_memory_mb,
            g.max_used_memory_kb / 1024.0 AS max_used_memory_mb,
            g.queue_id,
            g.wait_order,
            g.is_next_candidate,
            g.wait_time_ms,
            g.dop,
            g.query_cost,
            g.timeout_sec,
            g.resource_semaphore_id,
            SUBSTRING(t.text, 1, 400) AS statement_text
        FROM sys.dm_exec_query_memory_grants g
        OUTER APPLY sys.dm_exec_sql_text(g.sql_handle) t
        """)
        cols = [d[0] for d in cursor.description]
        grants = [dict(zip(cols, row)) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        grants.sort(key=lambda g: (g.get('requested_memory_mb') or 0), reverse=True)
        waiting = [g for g in grants if g.get('grant_time') is None]

        return {
            'semaphores': semaphores,
            'grants': grants[:20],
            'grant_count': len(grants),
            'waiting_for_grant_count': len(waiting),
            'waiting_sessions': [g['session_id'] for g in waiting],
        }
    except Exception as e:
        return {'error': str(e)}


# ===== ROOT CAUSE TOOLS (Phase 2: why is this specific session slow) =====

@tool
def get_live_execution_plan(session_id: int) -> Dict[str, Any]:
    """Get the in-flight execution plan for a running session, with ACTUAL row counts.

    This is the primary root cause tool. sys.dm_exec_query_statistics_xml returns the plan
    of a still-executing query including rows produced so far, which is what exposes
    estimate-vs-actual skew. Falls back to the cached (estimate-only) plan if the live plan
    is unavailable. Returns a parsed summary, not raw XML.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            r.session_id,
            r.status,
            r.wait_type,
            r.total_elapsed_time / 1000 AS elapsed_seconds,
            r.cpu_time AS cpu_time_ms,
            r.logical_reads,
            r.granted_query_memory * 8 / 1024.0 AS granted_memory_mb,
            r.dop,
            CAST(live.query_plan AS NVARCHAR(MAX)) AS live_plan_xml,
            CAST(cached.query_plan AS NVARCHAR(MAX)) AS cached_plan_xml,
            SUBSTRING(t.text, (r.statement_start_offset / 2) + 1,
                ((CASE r.statement_end_offset WHEN -1 THEN DATALENGTH(t.text)
                  ELSE r.statement_end_offset END - r.statement_start_offset) / 2) + 1
            ) AS statement_text
        FROM sys.dm_exec_requests r
        OUTER APPLY sys.dm_exec_query_statistics_xml(r.session_id) live
        OUTER APPLY sys.dm_exec_query_plan(r.plan_handle) cached
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) t
        WHERE r.session_id = %s
        """, (session_id,))

        cols = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {'error': f'No active request found for session_id {session_id}',
                    'hint': 'The query may have finished. Use get_active_requests to list live sessions.'}

        rec = dict(zip(cols, row))
        live_xml = rec.pop('live_plan_xml', None)
        cached_xml = rec.pop('cached_plan_xml', None)

        if live_xml:
            rec['plan_source'] = 'live (actual rows available)'
            rec['plan'] = _summarize_showplan(live_xml)
        elif cached_xml:
            rec['plan_source'] = 'cached (ESTIMATES ONLY - no actual rows)'
            rec['plan'] = _summarize_showplan(cached_xml)
        else:
            rec['plan_source'] = 'unavailable'
            rec['plan'] = None

        return rec
    except Exception as e:
        return {'error': str(e)}


# ===== SCHEMA CONTEXT TOOLS (Phase 3: is an index viable, or is a rewrite required) =====

@tool
def get_table_schema(table_name: str) -> Dict[str, Any]:
    """Get columns, data types and row count for a table.

    Required before recommending an index or a rewrite: data type mismatches across a join
    are what cause implicit conversions, and row counts determine whether a seek is worth it.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            c.name AS column_name,
            ty.name AS data_type,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable,
            c.is_identity,
            c.is_computed
        FROM sys.columns c
        INNER JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE c.object_id = OBJECT_ID(%s)
        """, (table_name,))
        cols = [d[0] for d in cursor.description]
        columns = [dict(zip(cols, row)) for row in cursor.fetchall()]

        cursor.execute("""
        SELECT SUM(p.rows) AS row_count
        FROM sys.partitions p
        WHERE p.object_id = OBJECT_ID(%s) AND p.index_id IN (0, 1)
        """, (table_name,))
        rc = cursor.fetchone()
        cursor.close()
        conn.close()

        if not columns:
            return {'error': f"Table '{table_name}' not found in database {DB_NAME}"}

        return {
            'table_name': table_name,
            'row_count': rc[0] if rc else None,
            'columns': columns,
            'column_count': len(columns),
        }
    except Exception as e:
        return {'error': str(e)}


@tool
def get_existing_indexes(table_name: str) -> Dict[str, Any]:
    """List indexes that already exist on a table, with key and included columns.

    Call this BEFORE recommending CREATE INDEX so the recommendation is not a duplicate of
    an existing index.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            i.name AS index_name,
            i.type_desc,
            i.is_unique,
            i.is_primary_key,
            i.has_filter,
            i.filter_definition,
            STRING_AGG(CASE WHEN ic.is_included_column = 0 THEN c.name END, ', ')
                WITHIN GROUP (ORDER BY ic.key_ordinal) AS key_columns,
            STRING_AGG(CASE WHEN ic.is_included_column = 1 THEN c.name END, ', ')
                AS included_columns
        FROM sys.indexes i
        LEFT JOIN sys.index_columns ic
               ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        LEFT JOIN sys.columns c
               ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(%s) AND i.type > 0
        GROUP BY i.name, i.type_desc, i.is_unique, i.is_primary_key,
                 i.has_filter, i.filter_definition
        """, (table_name,))
        cols = [d[0] for d in cursor.description]
        indexes = [dict(zip(cols, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        return {'table_name': table_name, 'indexes': indexes, 'count': len(indexes)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_statistics_health(table_name: str) -> Dict[str, Any]:
    """Get statistics freshness for a table: last update, sampling rate, rows modified since.

    Stale statistics produce cardinality underestimates that look exactly like a missing
    index. Check this BEFORE recommending an index - UPDATE STATISTICS is far cheaper.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            s.name AS stats_name,
            s.auto_created,
            sp.last_updated,
            sp.rows,
            sp.rows_sampled,
            CASE WHEN sp.rows > 0
                 THEN CAST(100.0 * sp.rows_sampled / sp.rows AS DECIMAL(5,2))
                 END AS sampled_percent,
            sp.modification_counter,
            CASE WHEN sp.rows > 0
                 THEN CAST(100.0 * sp.modification_counter / sp.rows AS DECIMAL(9,2))
                 END AS modified_percent,
            sp.steps
        FROM sys.stats s
        CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) sp
        WHERE s.object_id = OBJECT_ID(%s)
        """, (table_name,))
        cols = [d[0] for d in cursor.description]
        stats = [dict(zip(cols, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        stale = [s['stats_name'] for s in stats
                 if (s.get('modified_percent') or 0) >= 20]

        return {
            'table_name': table_name,
            'statistics': stats,
            'count': len(stats),
            'stale_candidates': stale,
            'note': 'modified_percent >= 20 is a common threshold for considering stats stale.',
        }
    except Exception as e:
        return {'error': str(e)}


@tool
def verify_plan_changed(object_name: str = None,
                        query_fragment: str = None,
                        within_minutes: int = 10,
                        baseline_plan_hash: str = None) -> Dict[str, Any]:
    """Verify that a NEW execution plan was compiled and is now in use, for ANY object or query.

    Direct evidence that a recompile or a schema change took effect, which is far stronger than
    inferring it from CPU movement. Works for stored procedures, triggers, views, functions, and
    for ad-hoc SQL via query_fragment.

    Provide object_name (e.g. "sp_MonthlyOrderReport", "dbo.MyView") OR query_fragment.

    Plan age is computed server-side with DATEDIFF against GETDATE(), so no timezone conversion
    is involved. A plan younger than within_minutes was compiled after your change.

    Useful property: sys.dm_exec_query_stats counters RESET when a plan is recompiled, so the
    avg_cpu_ms / avg_logical_reads returned here describe the NEW plan only. That makes them a
    clean per-execution before/after comparison, unaffected by other workload on the instance.

    IMPORTANT: these DMVs only record COMPLETED executions. If the object is still running its
    first execution since the change, there will be no new row yet - wait and re-check rather
    than concluding the plan did not change.

    Args:
        object_name: Object to inspect, e.g. "sp_MonthlyOrderReport" or "dbo.sp_MonthlyOrderReport"
        query_fragment: SQL text fragment, for ad-hoc statements with no owning object
        within_minutes: A plan compiled this recently counts as new (default 10)
        baseline_plan_hash: query_plan_hash captured before the change; if it differs now,
                            that is conclusive proof of a different plan
    """
    import re
    try:
        if not object_name and not query_fragment:
            return {'error': 'Provide either object_name or query_fragment'}

        target = (object_name or '').strip()
        if target and not re.match(
                r'^\[?[A-Za-z_][A-Za-z0-9_]*\]?(\.\[?[A-Za-z_][A-Za-z0-9_]*\]?)?$', target):
            return {'error': 'Invalid object name. Use [schema.]object with letters, digits '
                             'and underscores only.'}

        conn = get_db_connection()
        cursor = conn.cursor()
        result = {'object_name': target or None, 'query_fragment': query_fragment,
                  'within_minutes': within_minutes, 'object_level': None, 'statements': []}

        if target:
            cursor.execute("SELECT OBJECT_ID(%s)", (target,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                cursor.close()
                conn.close()
                return {'error': f"Object '{target}' not found in database {DB_NAME}"}

            # Object-level view: cached_time is when this object's plan entered the cache.
            cursor.execute("""
            SELECT
                OBJECT_NAME(ps.object_id) AS object_name,
                ps.cached_time,
                DATEDIFF(SECOND, ps.cached_time, GETDATE())          AS plan_age_seconds,
                ps.last_execution_time,
                DATEDIFF(SECOND, ps.last_execution_time, GETDATE())  AS last_execution_age_seconds,
                ps.execution_count,
                ps.total_worker_time  / NULLIF(ps.execution_count, 0) / 1000.0 AS avg_cpu_ms,
                ps.total_elapsed_time / NULLIF(ps.execution_count, 0) / 1000.0 AS avg_duration_ms,
                ps.total_logical_reads / NULLIF(ps.execution_count, 0)         AS avg_logical_reads,
                CONVERT(VARCHAR(128), ps.plan_handle, 1) AS plan_handle
            FROM sys.dm_exec_procedure_stats ps
            WHERE ps.object_id = OBJECT_ID(%s) AND ps.database_id = DB_ID()
            """, (target,))
            obj_rows = _fetch(cursor)
            result['object_level'] = obj_rows[0] if obj_rows else None

            stmt_sql = """
            SELECT
                qs.plan_generation_num,
                qs.creation_time,
                DATEDIFF(SECOND, qs.creation_time, GETDATE())         AS plan_age_seconds,
                qs.last_execution_time,
                DATEDIFF(SECOND, qs.last_execution_time, GETDATE())   AS last_execution_age_seconds,
                qs.execution_count,
                qs.total_worker_time  / NULLIF(qs.execution_count, 0) / 1000.0 AS avg_cpu_ms,
                qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 AS avg_duration_ms,
                qs.total_logical_reads / NULLIF(qs.execution_count, 0)         AS avg_logical_reads,
                CONVERT(VARCHAR(34), qs.query_plan_hash, 1) AS query_plan_hash,
                CONVERT(VARCHAR(34), qs.query_hash, 1)      AS query_hash,
                SUBSTRING(t.text, (qs.statement_start_offset / 2) + 1,
                    ((CASE qs.statement_end_offset WHEN -1 THEN DATALENGTH(t.text)
                      ELSE qs.statement_end_offset END - qs.statement_start_offset) / 2) + 1
                ) AS statement_text
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) t
            WHERE t.objectid = OBJECT_ID(%s)
            """
            cursor.execute(stmt_sql, (target,))
        else:
            cursor.execute("""
            SELECT
                qs.plan_generation_num,
                qs.creation_time,
                DATEDIFF(SECOND, qs.creation_time, GETDATE())         AS plan_age_seconds,
                qs.last_execution_time,
                DATEDIFF(SECOND, qs.last_execution_time, GETDATE())   AS last_execution_age_seconds,
                qs.execution_count,
                qs.total_worker_time  / NULLIF(qs.execution_count, 0) / 1000.0 AS avg_cpu_ms,
                qs.total_elapsed_time / NULLIF(qs.execution_count, 0) / 1000.0 AS avg_duration_ms,
                qs.total_logical_reads / NULLIF(qs.execution_count, 0)         AS avg_logical_reads,
                CONVERT(VARCHAR(34), qs.query_plan_hash, 1) AS query_plan_hash,
                CONVERT(VARCHAR(34), qs.query_hash, 1)      AS query_hash,
                SUBSTRING(t.text, 1, 300) AS statement_text
            FROM sys.dm_exec_query_stats qs
            CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) t
            WHERE t.text LIKE %s
            """, ('%' + query_fragment + '%',))

        statements = _fetch(cursor)
        cursor.close()
        conn.close()

        statements.sort(key=lambda s: (s.get('plan_age_seconds') if
                                       s.get('plan_age_seconds') is not None else 1 << 30))
        result['statements'] = statements[:20]
        result['statement_count'] = len(statements)

        threshold = int(within_minutes) * 60
        ages = [s['plan_age_seconds'] for s in statements
                if s.get('plan_age_seconds') is not None]
        if result['object_level'] and result['object_level'].get('plan_age_seconds') is not None:
            ages.append(result['object_level']['plan_age_seconds'])

        hashes = {s.get('query_plan_hash') for s in statements if s.get('query_plan_hash')}
        result['current_plan_hashes'] = sorted(hashes)

        if not ages:
            result['verdict'] = 'NO_DATA'
            result['reason'] = ('No cached plan statistics found. These DMVs only record '
                               'COMPLETED executions, so if the object is mid-execution since '
                               'the change, wait for it to finish and re-check.')
        elif baseline_plan_hash and hashes and baseline_plan_hash not in hashes:
            result['verdict'] = 'PLAN_CHANGED'
            result['reason'] = (f'query_plan_hash differs from baseline {baseline_plan_hash}. '
                                'Conclusive: a different plan is in use.')
        elif min(ages) <= threshold:
            result['verdict'] = 'PLAN_CHANGED'
            result['reason'] = (f'Youngest plan was compiled {min(ages)}s ago, within the '
                                f'{within_minutes} minute window.')
        else:
            result['verdict'] = 'PLAN_UNCHANGED'
            result['reason'] = (f'Youngest plan is {min(ages)}s old, older than the '
                                f'{within_minutes} minute window. The recompile or schema '
                                'change has not taken effect for this object yet.')

        result['youngest_plan_age_seconds'] = min(ages) if ages else None
        return result
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


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
   Use the tools for the phase the Supervisor names. If no phase is named, start with
   PHASE 1 (get_active_requests). Do NOT start with Query Store: it may be disabled, and
   live DMVs answer "what is happening now" without it. Only call Query Store tools after
   check_query_store_enabled confirms it is available.
6. If a tool returns no data or an error, return that fact as-is. Never invent values.
   Distinguish clearly between "tool returned an empty result" and "tool failed".

The Supervisor does ALL reasoning. You only execute tools and hand back data.

Tools, grouped by triage phase. Select by the phase named in the request:

PHASE 1 - what is running, what is it waiting on (always available, cheap):
- get_active_requests: Every live request with wait_type, granted_memory_mb, blocking_session_id,
  elapsed_seconds, plan_handle. Returns session_id values needed by Phase 2.
- get_memory_grants: Memory grant queue + per-query grants. Call when RESOURCE_SEMAPHORE is named.
- get_blocking_sessions: Blocking chains.
- get_slow_queries: Currently running queries over a duration threshold.

PHASE 2 - why is one specific session slow (requires session_id):
- get_live_execution_plan(session_id): In-flight plan with ACTUAL rows, estimate/actual skew,
  plan warnings (implicit conversions, spills, missing statistics) and memory grant detail.
- get_query_plan_from_cache(query_fragment): Cached ESTIMATE-ONLY plan. Use only when the
  query is not currently running.
- verify_plan_changed(object_name= or query_fragment=): Whether a NEW plan was compiled and is
  in use, for ANY object. Returns plan age, plan_generation_num, query_plan_hash, and
  per-execution avg_cpu_ms / avg_logical_reads for the current plan only. Use in PHASE 5.

PHASE 3 - is an index viable, or is a rewrite required (requires table_name):
- get_table_schema(table_name): Columns, data types, row count.
- get_existing_indexes(table_name): Indexes already present, with key and included columns.
- get_statistics_health(table_name): Stats freshness, sampling, rows modified since update.
- suggest_indexes: Advisory missing-index DMV. Corroboration only.
- get_index_usage: Index usage counters.

PHASE 4 - history and regression (requires Query Store):
- check_query_store_enabled: Availability. Call first before any Query Store tool.
- get_query_store_top_queries / get_query_store_regressed_queries / get_query_store_wait_stats
- get_query_execution_history / get_query_store_plan_summary
- get_expensive_queries_from_cache: Plan cache aggregates. NOTE: only records COMPLETED
  executions, so a long-running query in flight will be absent. Always pair with
  get_active_requests.

Return the raw tool results. Do not rank or format into a report - the Supervisor interprets the data."""

agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        # Phase 1 - triage
        get_active_requests,
        get_memory_grants,
        get_blocking_sessions,
        get_slow_queries,
        # Phase 2 - root cause
        get_live_execution_plan,
        get_query_plan_from_cache,
        verify_plan_changed,
        # Phase 3 - schema context for the fix decision
        get_table_schema,
        get_existing_indexes,
        get_statistics_health,
        suggest_indexes,
        get_index_usage,
        # Phase 4 - history / regression
        check_query_store_enabled,
        get_query_store_top_queries,
        get_query_store_regressed_queries,
        get_query_store_wait_stats,
        get_query_execution_history,
        get_query_store_plan_summary,
        get_expensive_queries_from_cache,
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

