import boto3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from strands import tool
from config.settings import DB_INSTANCE_ID, DB_SECRET_ID, AWS_REGION, SNS_TOPIC_NAME
from tools.shared_utils import db_cursor, fetch_all, send_notification


def _validate_int(value, name, min_val=1, max_val=10000):
    """Validate and clamp an integer parameter to a safe range."""
    val = int(value)
    if val < min_val or val > max_val:
        raise ValueError(f"{name} must be between {min_val} and {max_val}")
    return val


_ORDER_BY_METRICS = {
    "cpu": "qrs.avg_cpu_time DESC",
    "duration": "qrs.avg_duration DESC",
    "io": "qrs.avg_logical_io_reads DESC",
    "memory": "qrs.avg_query_max_used_memory DESC",
}

_CACHE_ORDER_BY_METRICS = {
    "cpu": "qs.total_worker_time DESC",
    "duration": "qs.total_elapsed_time DESC",
    "reads": "qs.total_logical_reads DESC",
    "writes": "qs.total_logical_writes DESC",
}


# ===== QUERY STORE TOOLS =====

@tool
def check_query_store_enabled() -> Dict[str, Any]:
    """Check if Query Store is enabled and get configuration"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT actual_state_desc, readonly_reason, desired_state_desc,
                       current_storage_size_mb, max_storage_size_mb, query_capture_mode_desc
                FROM sys.database_query_store_options
            """)
            row = cursor.fetchone()
        if row:
            return {
                'enabled': row[0] in ('READ_WRITE', 'READ_ONLY'), 'state': row[0],
                'readonly_reason': row[1], 'desired_state': row[2],
                'storage_used_mb': row[3], 'storage_max_mb': row[4], 'capture_mode': row[5]
            }
        return {'enabled': False, 'error': 'Query Store not configured'}
    except Exception as e:
        return {'enabled': False, 'error': str(e)}


@tool
def get_query_store_top_queries(hours_back: int = 24, top_n: int = 10, metric: str = "cpu") -> Dict[str, Any]:
    """Get top resource-consuming queries from Query Store. Metric: cpu, duration, io, memory"""
    try:
        hours_back = _validate_int(hours_back, "hours_back", 1, 8760)
        top_n = _validate_int(top_n, "top_n", 1, 100)
        order_by = _ORDER_BY_METRICS.get(metric, _ORDER_BY_METRICS["cpu"])
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT TOP %d
                    qsq.query_id, SUBSTRING(CAST(qst.query_sql_text AS NVARCHAR(MAX)), 1, 500) as query_text,
                    qrs.avg_cpu_time / 1000 as avg_cpu_ms, qrs.avg_duration / 1000 as avg_duration_ms,
                    qrs.avg_logical_io_reads, qrs.avg_query_max_used_memory * 8 / 1024 as avg_memory_mb,
                    qrs.count_executions, qrs.last_execution_time
                FROM sys.query_store_query qsq
                JOIN sys.query_store_query_text qst ON qsq.query_text_id = qst.query_text_id
                JOIN sys.query_store_plan qp ON qsq.query_id = qp.query_id
                JOIN sys.query_store_runtime_stats qrs ON qp.plan_id = qrs.plan_id
                JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                WHERE qrsi.start_time >= DATEADD(hour, -%d, GETUTCDATE())
                ORDER BY """
                + order_by,
                (top_n, hours_back),
            )
            results = fetch_all(cursor)
        return {'queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_query_store_regressed_queries(hours_back: int = 24) -> Dict[str, Any]:
    """Detect queries that regressed in performance (comparing recent vs historical)"""
    try:
        hours_back = _validate_int(hours_back, "hours_back", 1, 8760)
        with db_cursor() as cursor:
            cursor.execute(
                """
                WITH recent_stats AS (
                    SELECT qp.query_id, AVG(qrs.avg_cpu_time) as recent_cpu, AVG(qrs.avg_duration) as recent_duration
                    FROM sys.query_store_runtime_stats qrs
                    JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                    JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
                    WHERE qrsi.start_time >= DATEADD(hour, -%d, GETUTCDATE())
                    GROUP BY qp.query_id
                ),
                historical_stats AS (
                    SELECT qp.query_id, AVG(qrs.avg_cpu_time) as hist_cpu, AVG(qrs.avg_duration) as hist_duration
                    FROM sys.query_store_runtime_stats qrs
                    JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                    JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
                    WHERE qrsi.start_time < DATEADD(hour, -%d, GETUTCDATE())
                    GROUP BY qp.query_id
                )
                SELECT TOP 10
                    q.query_id, SUBSTRING(CAST(qt.query_sql_text AS NVARCHAR(MAX)), 1, 500) as query_text,
                    rs.recent_cpu / 1000 as recent_cpu_ms, hs.hist_cpu / 1000 as historical_cpu_ms,
                    CAST((rs.recent_cpu - hs.hist_cpu) / hs.hist_cpu * 100 AS DECIMAL(10,2)) as cpu_regression_pct,
                    rs.recent_duration / 1000 as recent_duration_ms, hs.hist_duration / 1000 as historical_duration_ms
                FROM recent_stats rs
                JOIN historical_stats hs ON rs.query_id = hs.query_id
                JOIN sys.query_store_query q ON rs.query_id = q.query_id
                JOIN sys.query_store_query_text qt ON q.query_text_id = qt.query_text_id
                WHERE rs.recent_cpu > hs.hist_cpu * 1.5
                ORDER BY cpu_regression_pct DESC
                """,
                (hours_back, hours_back),
            )
            results = fetch_all(cursor)
        return {'regressed_queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_query_store_wait_stats(query_id: int = None, hours_back: int = 24) -> Dict[str, Any]:
    """Get wait statistics from Query Store for specific query or all queries"""
    try:
        hours_back = _validate_int(hours_back, "hours_back", 1, 8760)
        with db_cursor() as cursor:
            if query_id is not None:
                query_id = _validate_int(query_id, "query_id", 0, 2**31)
                cursor.execute(
                    """
                    SELECT TOP 20 qp.query_id, qsws.wait_category_desc, qsws.avg_query_wait_time_ms,
                           qsws.total_query_wait_time_ms, qsws.execution_type_desc
                    FROM sys.query_store_wait_stats qsws
                    JOIN sys.query_store_plan qp ON qsws.plan_id = qp.plan_id
                    JOIN sys.query_store_runtime_stats_interval qrsi ON qsws.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                    WHERE qrsi.start_time >= DATEADD(hour, -%d, GETUTCDATE()) AND qp.query_id = %d
                    ORDER BY qsws.avg_query_wait_time_ms DESC
                    """,
                    (hours_back, query_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT TOP 20 qp.query_id, qsws.wait_category_desc, qsws.avg_query_wait_time_ms,
                           qsws.total_query_wait_time_ms, qsws.execution_type_desc
                    FROM sys.query_store_wait_stats qsws
                    JOIN sys.query_store_plan qp ON qsws.plan_id = qp.plan_id
                    JOIN sys.query_store_runtime_stats_interval qrsi ON qsws.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                    WHERE qrsi.start_time >= DATEADD(hour, -%d, GETUTCDATE())
                    ORDER BY qsws.avg_query_wait_time_ms DESC
                    """,
                    (hours_back,),
                )
            results = fetch_all(cursor)
        return {'wait_stats': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_query_execution_history(query_id: int, hours_back: int = 168) -> Dict[str, Any]:
    """Get execution history timeline for a specific query (up to 7 days)"""
    try:
        query_id = _validate_int(query_id, "query_id", 0, 2**31)
        hours_back = _validate_int(hours_back, "hours_back", 1, 8760)
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT qrsi.start_time, qrsi.end_time, qrs.count_executions,
                       qrs.avg_cpu_time / 1000 as avg_cpu_ms, qrs.avg_duration / 1000 as avg_duration_ms,
                       qrs.avg_logical_io_reads, qrs.avg_query_max_used_memory * 8 / 1024 as avg_memory_mb
                FROM sys.query_store_runtime_stats qrs
                JOIN sys.query_store_runtime_stats_interval qrsi ON qrs.runtime_stats_interval_id = qrsi.runtime_stats_interval_id
                JOIN sys.query_store_plan qp ON qrs.plan_id = qp.plan_id
                WHERE qp.query_id = %d AND qrsi.start_time >= DATEADD(hour, -%d, GETUTCDATE())
                ORDER BY qrsi.start_time
                """,
                (query_id, hours_back),
            )
            results = fetch_all(cursor)
        return {'timeline': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_query_store_plan_summary(query_id: int) -> Dict[str, Any]:
    """Get execution plan summary for a specific query"""
    try:
        query_id = _validate_int(query_id, "query_id", 0, 2**31)
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT qp.plan_id, qp.is_forced_plan, qrs.avg_cpu_time / 1000 as avg_cpu_ms,
                       qrs.avg_duration / 1000 as avg_duration_ms, qrs.count_executions,
                       qrs.first_execution_time, qrs.last_execution_time
                FROM sys.query_store_plan qp
                JOIN sys.query_store_runtime_stats qrs ON qp.plan_id = qrs.plan_id
                WHERE qp.query_id = %d
                ORDER BY qrs.avg_cpu_time DESC
                """,
                (query_id,),
            )
            results = fetch_all(cursor)
        return {'plans': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


# ===== DMV TOOLS =====

@tool
def get_slow_queries(threshold_seconds: int = 5) -> Dict[str, Any]:
    """Get currently running slow queries from sys.dm_exec_requests"""
    try:
        threshold_seconds = _validate_int(threshold_seconds, "threshold_seconds", 0, 86400)
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT TOP 10 r.session_id, r.status, r.command, r.cpu_time,
                       r.total_elapsed_time / 1000 as elapsed_seconds, r.logical_reads, r.writes, r.blocking_session_id,
                       SUBSTRING(st.text, (r.statement_start_offset/2)+1,
                           ((CASE r.statement_end_offset WHEN -1 THEN DATALENGTH(st.text) ELSE r.statement_end_offset END - r.statement_start_offset)/2) + 1) AS query_text
                FROM sys.dm_exec_requests r
                CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
                WHERE r.session_id > 50 AND r.total_elapsed_time / 1000 > %d
                ORDER BY r.total_elapsed_time DESC
                """,
                (threshold_seconds,),
            )
            results = fetch_all(cursor)
        return {'slow_queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_blocking_sessions() -> Dict[str, Any]:
    """Get blocking sessions and what they're blocking"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT blocking.session_id AS blocking_session_id, blocked.session_id AS blocked_session_id,
                   blocking_text.text AS blocking_query, blocked_text.text AS blocked_query,
                   blocked.wait_time / 1000 AS wait_seconds, blocked.wait_type
            FROM sys.dm_exec_requests blocked
            INNER JOIN sys.dm_exec_requests blocking ON blocked.blocking_session_id = blocking.session_id
            CROSS APPLY sys.dm_exec_sql_text(blocking.sql_handle) blocking_text
            CROSS APPLY sys.dm_exec_sql_text(blocked.sql_handle) blocked_text
            WHERE blocked.blocking_session_id > 0
            """)
            results = fetch_all(cursor)
        return {'blocking_sessions': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_query_plan_from_cache(query_fragment: str) -> Dict[str, Any]:
    """Get execution plan from plan cache for queries matching the fragment"""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT TOP 5 SUBSTRING(st.text, 1, 500) as query_text, qs.execution_count,
                       qs.total_worker_time / 1000 as total_cpu_ms, qs.total_elapsed_time / 1000 as total_duration_ms,
                       qs.total_logical_reads, qs.total_logical_writes,
                       CAST(qp.query_plan AS NVARCHAR(MAX)) as execution_plan_xml
                FROM sys.dm_exec_query_stats qs
                CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
                CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp
                WHERE st.text LIKE %s
                ORDER BY qs.total_worker_time DESC
                """,
                ('%' + query_fragment + '%',),
            )
            results = fetch_all(cursor)
        for result in results:
            if result.get('execution_plan_xml'):
                result['execution_plan_xml'] = result['execution_plan_xml'][:1000] + '...(truncated)'
        return {'plans': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_expensive_queries_from_cache(top_n: int = 10, metric: str = "cpu") -> Dict[str, Any]:
    """Get top expensive queries from plan cache (since last restart). Metric: cpu, duration, reads, writes"""
    try:
        top_n = _validate_int(top_n, "top_n", 1, 100)
        order_by = _CACHE_ORDER_BY_METRICS.get(metric, _CACHE_ORDER_BY_METRICS["cpu"])
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT TOP %d SUBSTRING(st.text, 1, 500) as query_text, qs.execution_count,
                       qs.total_worker_time / 1000 as total_cpu_ms, qs.total_elapsed_time / 1000 as total_duration_ms,
                       qs.total_logical_reads, qs.total_logical_writes, qs.creation_time, qs.last_execution_time
                FROM sys.dm_exec_query_stats qs
                CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
                ORDER BY """
                + order_by,
                (top_n,),
            )
            results = fetch_all(cursor)
        return {'queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def suggest_indexes(table_name: str = None) -> Dict[str, Any]:
    """Get missing index recommendations from DMVs with CREATE INDEX statements"""
    try:
        with db_cursor() as cursor:
            if table_name is not None:
                cursor.execute(
                    """
                    SELECT TOP 10 OBJECT_NAME(d.object_id, d.database_id) AS table_name,
                           d.equality_columns, d.inequality_columns, d.included_columns,
                           s.avg_total_user_cost * s.avg_user_impact * (s.user_seeks + s.user_scans) AS improvement_measure,
                           'CREATE INDEX IX_' + OBJECT_NAME(d.object_id, d.database_id) + '_' +
                               REPLACE(REPLACE(REPLACE(ISNULL(d.equality_columns, ''), ', ', '_'), '[', ''), ']', '') +
                               CASE WHEN d.inequality_columns IS NOT NULL THEN '_' +
                                   REPLACE(REPLACE(REPLACE(d.inequality_columns, ', ', '_'), '[', ''), ']', '') ELSE '' END +
                           ' ON ' + d.statement + ' (' +
                               ISNULL(d.equality_columns, '') +
                               CASE WHEN d.equality_columns IS NOT NULL AND d.inequality_columns IS NOT NULL THEN ', ' ELSE '' END +
                               ISNULL(d.inequality_columns, '') + ')' +
                               CASE WHEN d.included_columns IS NOT NULL THEN ' INCLUDE (' + d.included_columns + ')' ELSE '' END
                           AS create_index_statement,
                           s.user_seeks, s.user_scans, s.last_user_seek, s.last_user_scan
                    FROM sys.dm_db_missing_index_details d
                    INNER JOIN sys.dm_db_missing_index_groups g ON d.index_handle = g.index_handle
                    INNER JOIN sys.dm_db_missing_index_group_stats s ON g.index_group_handle = s.group_handle
                    WHERE d.database_id = DB_ID() AND OBJECT_NAME(d.object_id, d.database_id) = %s
                    ORDER BY improvement_measure DESC
                    """,
                    (table_name,),
                )
            else:
                cursor.execute("""
                    SELECT TOP 10 OBJECT_NAME(d.object_id, d.database_id) AS table_name,
                           d.equality_columns, d.inequality_columns, d.included_columns,
                           s.avg_total_user_cost * s.avg_user_impact * (s.user_seeks + s.user_scans) AS improvement_measure,
                           'CREATE INDEX IX_' + OBJECT_NAME(d.object_id, d.database_id) + '_' +
                               REPLACE(REPLACE(REPLACE(ISNULL(d.equality_columns, ''), ', ', '_'), '[', ''), ']', '') +
                               CASE WHEN d.inequality_columns IS NOT NULL THEN '_' +
                                   REPLACE(REPLACE(REPLACE(d.inequality_columns, ', ', '_'), '[', ''), ']', '') ELSE '' END +
                           ' ON ' + d.statement + ' (' +
                               ISNULL(d.equality_columns, '') +
                               CASE WHEN d.equality_columns IS NOT NULL AND d.inequality_columns IS NOT NULL THEN ', ' ELSE '' END +
                               ISNULL(d.inequality_columns, '') + ')' +
                               CASE WHEN d.included_columns IS NOT NULL THEN ' INCLUDE (' + d.included_columns + ')' ELSE '' END
                           AS create_index_statement,
                           s.user_seeks, s.user_scans, s.last_user_seek, s.last_user_scan
                    FROM sys.dm_db_missing_index_details d
                    INNER JOIN sys.dm_db_missing_index_groups g ON d.index_handle = g.index_handle
                    INNER JOIN sys.dm_db_missing_index_group_stats s ON g.index_group_handle = s.group_handle
                    WHERE d.database_id = DB_ID()
                    ORDER BY improvement_measure DESC
                """)
            results = fetch_all(cursor)
        return {'missing_indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_index_usage() -> Dict[str, Any]:
    """Get index usage statistics to identify unused indexes"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 20 OBJECT_NAME(s.object_id) AS table_name, i.name AS index_name,
                   s.user_seeks, s.user_scans, s.user_lookups, s.user_updates,
                   CASE WHEN s.user_seeks + s.user_scans + s.user_lookups = 0 THEN 'UNUSED'
                        WHEN s.user_updates > (s.user_seeks + s.user_scans + s.user_lookups) * 10 THEN 'EXPENSIVE'
                        ELSE 'USED' END AS usage_status
            FROM sys.dm_db_index_usage_stats s
            INNER JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
            WHERE s.database_id = DB_ID() AND OBJECTPROPERTY(s.object_id, 'IsUserTable') = 1
            ORDER BY s.user_updates DESC
            """)
            results = fetch_all(cursor)
        return {'index_usage': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


# ===== SNS =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    return send_notification(subject, message, severity, agent_name="Query Performance Agent")
