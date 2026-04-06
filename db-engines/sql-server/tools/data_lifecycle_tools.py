import boto3
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from strands import tool
from config.settings import DB_INSTANCE_ID, DB_SECRET_ID, AWS_REGION, SNS_TOPIC_NAME
from tools.shared_utils import db_cursor, fetch_all, send_notification


def calculate_period(minutes_back):
    if minutes_back <= 1440:
        return 60
    elif minutes_back <= 4320:
        return 300
    else:
        return 600


def get_instance_age_hours():
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        age = datetime.now(timezone.utc) - response['DBInstances'][0]['InstanceCreateTime']
        return age.total_seconds() / 3600
    except Exception:
        return None


def _clamp_days(days_back):
    """Clamp days_back to instance age"""
    age = get_instance_age_hours()
    if age and age < days_back * 24:
        return max(1, int(age / 24))
    return days_back


# ===== CLOUDWATCH STORAGE TOOLS =====

@tool
def get_storage_metrics(days_back: int = 7) -> Dict[str, Any]:
    """Get storage usage and growth trends from CloudWatch with timeline breakdown"""
    try:
        days_back = _clamp_days(days_back)
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        metrics = {}
        for metric_name in ['FreeStorageSpace', 'AllocatedStorage']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Minimum', 'Maximum']
            )
            if response['Datapoints']:
                dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                vals = [dp['Average'] / (1024**3) for dp in dps]
                metrics[metric_name] = {
                    'current_gb': round(vals[-1], 2), 'initial_gb': round(vals[0], 2),
                    'change_gb': round(vals[-1] - vals[0], 2),
                    'min_gb': round(min(vals), 2), 'max_gb': round(max(vals), 2),
                    'avg_gb': round(sum(vals) / len(vals), 2),
                    'datapoint_count': len(dps), 'period_seconds': period
                }
        return metrics if metrics else {'error': 'No storage data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_iops_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get IOPS trends from CloudWatch with timeline breakdown"""
    try:
        days_back = _clamp_days(days_back)
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        iops = {}
        for metric_name in ['ReadIOPS', 'WriteIOPS']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum', 'Minimum']
            )
            if response['Datapoints']:
                dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avgs = [dp['Average'] for dp in dps]
                maxs = [dp['Maximum'] for dp in dps]
                iops[metric_name] = {
                    'current_avg': round(avgs[-1], 2), 'current_max': round(maxs[-1], 2),
                    'period_avg': round(sum(avgs) / len(avgs), 2),
                    'period_max': round(max(maxs), 2), 'period_min': round(min(avgs), 2),
                    'datapoint_count': len(dps), 'period_seconds': period
                }
        return iops if iops else {'error': 'No IOPS data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_throughput_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get read/write throughput trends from CloudWatch"""
    try:
        days_back = _clamp_days(days_back)
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        throughput = {}
        for metric_name in ['ReadThroughput', 'WriteThroughput']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum', 'Minimum']
            )
            if response['Datapoints']:
                dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avgs = [dp['Average'] / (1024**2) for dp in dps]
                maxs = [dp['Maximum'] / (1024**2) for dp in dps]
                throughput[metric_name] = {
                    'current_avg_mbps': round(avgs[-1], 2), 'current_max_mbps': round(maxs[-1], 2),
                    'period_avg_mbps': round(sum(avgs) / len(avgs), 2),
                    'period_max_mbps': round(max(maxs), 2), 'period_min_mbps': round(min(avgs), 2),
                    'datapoint_count': len(dps)
                }
        return throughput if throughput else {'error': 'No throughput data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_latency_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get read/write latency trends from CloudWatch"""
    try:
        days_back = _clamp_days(days_back)
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        latency = {}
        for metric_name in ['ReadLatency', 'WriteLatency']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum', 'Minimum']
            )
            if response['Datapoints']:
                dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avgs = [dp['Average'] * 1000 for dp in dps]
                maxs = [dp['Maximum'] * 1000 for dp in dps]
                latency[metric_name] = {
                    'current_avg_ms': round(avgs[-1], 2), 'current_max_ms': round(maxs[-1], 2),
                    'period_avg_ms': round(sum(avgs) / len(avgs), 2),
                    'period_max_ms': round(max(maxs), 2), 'period_min_ms': round(min(avgs), 2),
                    'datapoint_count': len(dps)
                }
        return latency if latency else {'error': 'No latency data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_queue_depth_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get disk queue depth trends from CloudWatch (bottleneck indicator)"""
    try:
        days_back = _clamp_days(days_back)
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='DiskQueueDepth',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum', 'Minimum']
        )
        if response['Datapoints']:
            dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            avgs = [dp['Average'] for dp in dps]
            maxs = [dp['Maximum'] for dp in dps]
            return {
                'current_avg': round(avgs[-1], 2), 'current_max': round(maxs[-1], 2),
                'period_avg': round(sum(avgs) / len(avgs), 2),
                'period_max': round(max(maxs), 2), 'period_min': round(min(avgs), 2),
                'datapoint_count': len(dps), 'bottleneck_warning': max(maxs) > 1.0
            }
        return {'error': 'No queue depth data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def analyze_storage_growth(days_back: int = 30) -> Dict[str, Any]:
    """Analyze storage growth trends"""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(days_back * 24 * 60)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='FreeStorageSpace',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average']
        )
        if response['Datapoints']:
            dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            first_free = dps[0]['Average'] / (1024**3)
            latest_free = dps[-1]['Average'] / (1024**3)
            used_growth = first_free - latest_free
            days_elapsed = (dps[-1]['Timestamp'] - dps[0]['Timestamp']).days
            daily_growth = used_growth / days_elapsed if days_elapsed > 0 else 0
            days_until_full = latest_free / daily_growth if daily_growth > 0 else float('inf')
            return {
                'days_analyzed': days_back, 'initial_free_gb': round(first_free, 2),
                'current_free_gb': round(latest_free, 2), 'growth_gb': round(used_growth, 2),
                'daily_growth_gb': round(daily_growth, 2),
                'days_until_full': round(days_until_full, 0) if days_until_full != float('inf') else 'N/A'
            }
        return {'error': 'No storage data available'}
    except Exception as e:
        return {'error': str(e)}


# ===== STORAGE CONFIGURATION =====

@tool
def get_storage_configuration() -> Dict[str, Any]:
    """Get RDS storage configuration (type, IOPS, throughput)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = response['DBInstances'][0]
        config = {
            'storage_type': db['StorageType'], 'allocated_storage_gb': db['AllocatedStorage'],
            'max_allocated_storage_gb': db.get('MaxAllocatedStorage'), 'storage_encrypted': db['StorageEncrypted']
        }
        if 'Iops' in db: config['provisioned_iops'] = db['Iops']
        if 'StorageThroughput' in db: config['provisioned_throughput_mbps'] = db['StorageThroughput']
        return config
    except Exception as e:
        return {'error': str(e)}


@tool
def recommend_storage_upgrade() -> Dict[str, Any]:
    """Analyze metrics and recommend storage type upgrade"""
    try:
        config_result = get_storage_configuration()
        if 'error' in config_result: return config_result
        storage_type = config_result['storage_type']
        iops_result = get_iops_trends(days_back=1)
        latency_result = get_latency_trends(days_back=1)
        queue_result = get_queue_depth_trends(days_back=1)
        recommendations = []
        if 'ReadLatency' in latency_result and latency_result['ReadLatency']['period_avg_ms'] > 20:
            recommendations.append({'issue': 'High read latency', 'current_avg_ms': latency_result['ReadLatency']['period_avg_ms'],
                                     'recommendation': 'Consider upgrading to io2 for lower latency'})
        if 'bottleneck_warning' in queue_result and queue_result['bottleneck_warning']:
            recommendations.append({'issue': 'High disk queue depth', 'current_max': queue_result['period_max'],
                                     'recommendation': 'Storage cannot keep up with demand - upgrade to higher IOPS'})
        if storage_type == 'gp2':
            recommendations.append({'issue': 'Using gp2 storage',
                                     'recommendation': 'Upgrade to gp3 for better price/performance (20% cost savings, better baseline performance)'})
        if storage_type in ['gp2', 'gp3']:
            read_iops = iops_result.get('ReadIOPS', {}).get('period_max', 0)
            write_iops = iops_result.get('WriteIOPS', {}).get('period_max', 0)
            total_iops = read_iops + write_iops
            if storage_type == 'gp2':
                gp2_limit = min(config_result['allocated_storage_gb'] * 3, 16000)
                if total_iops > gp2_limit * 0.8:
                    recommendations.append({'issue': 'Approaching gp2 IOPS limit', 'current_iops': round(total_iops, 0),
                                             'gp2_limit': gp2_limit, 'recommendation': 'Upgrade to gp3 with provisioned IOPS or io2'})
        return {'current_storage_type': storage_type, 'recommendations': recommendations, 'recommendation_count': len(recommendations)}
    except Exception as e:
        return {'error': str(e)}


# ===== DMV STORAGE TOOLS =====

@tool
def get_database_size() -> Dict[str, Any]:
    """Get total database size"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT DB_NAME(database_id) AS database_name, SUM(size * 8.0 / 1024) AS size_mb
            FROM sys.master_files WHERE database_id > 4 GROUP BY database_id ORDER BY size_mb DESC
            """)
            results = fetch_all(cursor)
        return {'databases': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_table_sizes() -> Dict[str, Any]:
    """Get table sizes sorted by space used"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 20 t.NAME AS table_name, s.Name AS schema_name, p.rows AS row_count,
                   SUM(a.total_pages) * 8 / 1024 AS total_space_mb, SUM(a.used_pages) * 8 / 1024 AS used_space_mb,
                   (SUM(a.total_pages) - SUM(a.used_pages)) * 8 / 1024 AS unused_space_mb
            FROM sys.tables t
            INNER JOIN sys.indexes i ON t.OBJECT_ID = i.object_id
            INNER JOIN sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
            INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
            LEFT OUTER JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE t.NAME NOT LIKE 'dt%' AND t.is_ms_shipped = 0 AND i.OBJECT_ID > 255
            GROUP BY t.Name, s.Name, p.Rows ORDER BY total_space_mb DESC
            """)
            results = fetch_all(cursor)
        return {'tables': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_index_sizes() -> Dict[str, Any]:
    """Get index sizes to identify large indexes"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 20 OBJECT_NAME(i.object_id) AS table_name, i.name AS index_name,
                   i.type_desc AS index_type, SUM(s.used_page_count) * 8 / 1024 AS index_size_mb
            FROM sys.dm_db_partition_stats s
            INNER JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
            WHERE OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1
            GROUP BY i.object_id, i.name, i.type_desc ORDER BY index_size_mb DESC
            """)
            results = fetch_all(cursor)
        return {'indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def identify_old_data(table_name: str, date_column: str, days_old: int = 365) -> Dict[str, Any]:
    """Identify old data candidates for archival"""
    try:
        with db_cursor() as cursor:
            cursor.execute(f"""
            SELECT COUNT(*) as old_record_count, MIN({date_column}) as oldest_date, MAX({date_column}) as newest_old_date
            FROM {table_name} WHERE {date_column} < DATEADD(day, -{days_old}, GETDATE())
            """)
            result = cursor.fetchone()
        if result:
            return {'table_name': table_name, 'old_record_count': result[0],
                    'oldest_date': result[1].isoformat() if result[1] else None,
                    'newest_old_date': result[2].isoformat() if result[2] else None, 'days_threshold': days_old}
        return {'error': 'No data found'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_fragmentation_status() -> Dict[str, Any]:
    """Get index fragmentation status"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 20 OBJECT_NAME(ips.object_id) AS table_name, i.name AS index_name,
                   ips.index_type_desc, ips.avg_fragmentation_in_percent, ips.page_count
            FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
            INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
            WHERE ips.avg_fragmentation_in_percent > 10 AND ips.page_count > 1000
            ORDER BY ips.avg_fragmentation_in_percent DESC
            """)
            results = fetch_all(cursor)
        return {'fragmented_indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def check_backup_status() -> Dict[str, Any]:
    """Check backup status and retention"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = db_response['DBInstances'][0]
        snapshot_response = rds_client.describe_db_snapshots(DBInstanceIdentifier=DB_INSTANCE_ID, MaxRecords=20)
        snapshots = [{'snapshot_id': s['DBSnapshotIdentifier'], 'snapshot_create_time': s['SnapshotCreateTime'].isoformat(),
                      'status': s['Status'], 'type': s['SnapshotType'], 'allocated_storage': s['AllocatedStorage']}
                     for s in snapshot_response.get('DBSnapshots', [])]
        return {
            'backup_retention_period': db['BackupRetentionPeriod'], 'preferred_backup_window': db['PreferredBackupWindow'],
            'latest_restorable_time': db.get('LatestRestorableTime', 'N/A').isoformat() if db.get('LatestRestorableTime') != 'N/A' else 'N/A',
            'recent_snapshots': snapshots, 'snapshot_count': len(snapshots)
        }
    except Exception as e:
        return {'error': str(e)}


# ===== TEMPDB TOOLS =====

@tool
def get_tempdb_size() -> Dict[str, Any]:
    """Get TempDB current size, used space, and free space per file"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT name AS file_name, physical_name, size * 8.0 / 1024 AS size_mb,
                   FILEPROPERTY(name, 'SpaceUsed') * 8.0 / 1024 AS used_mb,
                   (size - FILEPROPERTY(name, 'SpaceUsed')) * 8.0 / 1024 AS free_mb, growth, is_percent_growth
            FROM tempdb.sys.database_files ORDER BY file_id
            """)
            results = fetch_all(cursor)
        total_size = sum(r['size_mb'] for r in results)
        total_used = sum(r['used_mb'] for r in results)
        return {'files': results, 'file_count': len(results), 'total_size_mb': round(total_size, 2),
                'total_used_mb': round(total_used, 2), 'total_free_mb': round(total_size - total_used, 2),
                'usage_percent': round((total_used / total_size * 100) if total_size > 0 else 0, 2)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_tempdb_space_usage_by_session() -> Dict[str, Any]:
    """Get TempDB space usage by session"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 10 s.session_id, s.login_name, s.host_name, s.program_name,
                   SUM(u.user_objects_alloc_page_count) * 8.0 / 1024 AS user_objects_mb,
                   SUM(u.internal_objects_alloc_page_count) * 8.0 / 1024 AS internal_objects_mb,
                   SUM(u.user_objects_alloc_page_count + u.internal_objects_alloc_page_count) * 8.0 / 1024 AS total_mb
            FROM sys.dm_db_session_space_usage u
            INNER JOIN sys.dm_exec_sessions s ON u.session_id = s.session_id
            WHERE (u.user_objects_alloc_page_count + u.internal_objects_alloc_page_count) > 0
            GROUP BY s.session_id, s.login_name, s.host_name, s.program_name ORDER BY total_mb DESC
            """)
            results = fetch_all(cursor)
        return {'sessions': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_tempdb_space_usage_by_query() -> Dict[str, Any]:
    """Get TempDB space usage by currently running queries"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT TOP 10 r.session_id, r.status, r.command,
                   SUBSTRING(st.text, (r.statement_start_offset/2)+1,
                       ((CASE r.statement_end_offset WHEN -1 THEN DATALENGTH(st.text) ELSE r.statement_end_offset END - r.statement_start_offset)/2) + 1) AS query_text,
                   t.user_objects_alloc_page_count * 8.0 / 1024 AS user_objects_mb,
                   t.internal_objects_alloc_page_count * 8.0 / 1024 AS internal_objects_mb,
                   (t.user_objects_alloc_page_count + t.internal_objects_alloc_page_count) * 8.0 / 1024 AS total_mb
            FROM sys.dm_exec_requests r
            CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
            INNER JOIN sys.dm_db_task_space_usage t ON r.session_id = t.session_id AND r.request_id = t.request_id
            WHERE (t.user_objects_alloc_page_count + t.internal_objects_alloc_page_count) > 0
            ORDER BY total_mb DESC
            """)
            results = fetch_all(cursor)
        return {'queries': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_tempdb_contention() -> Dict[str, Any]:
    """Get TempDB PFS/SGAM/GAM page latch contention"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT wait_type, waiting_tasks_count, wait_time_ms, max_wait_time_ms, signal_wait_time_ms
            FROM sys.dm_os_wait_stats WHERE wait_type LIKE 'PAGELATCH%' AND wait_time_ms > 0
            ORDER BY wait_time_ms DESC
            """)
            results = fetch_all(cursor)
        return {'latch_waits': results, 'contention_detected': any(r['wait_time_ms'] > 10000 for r in results), 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_tempdb_io_stats() -> Dict[str, Any]:
    """Get TempDB file I/O latency and stalls"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT mf.name AS file_name, mf.physical_name, vfs.num_of_reads, vfs.num_of_writes,
                   vfs.num_of_bytes_read / 1024 / 1024 AS mb_read, vfs.num_of_bytes_written / 1024 / 1024 AS mb_written,
                   vfs.io_stall_read_ms, vfs.io_stall_write_ms,
                   CASE WHEN vfs.num_of_reads > 0 THEN vfs.io_stall_read_ms / vfs.num_of_reads ELSE 0 END AS avg_read_latency_ms,
                   CASE WHEN vfs.num_of_writes > 0 THEN vfs.io_stall_write_ms / vfs.num_of_writes ELSE 0 END AS avg_write_latency_ms
            FROM sys.dm_io_virtual_file_stats(DB_ID('tempdb'), NULL) vfs
            INNER JOIN tempdb.sys.master_files mf ON vfs.file_id = mf.file_id AND vfs.database_id = mf.database_id
            ORDER BY vfs.io_stall_read_ms + vfs.io_stall_write_ms DESC
            """)
            results = fetch_all(cursor)
        return {'file_io_stats': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def check_tempdb_file_configuration() -> Dict[str, Any]:
    """Check TempDB file configuration (count, sizes, growth)"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT name, size * 8.0 / 1024 AS size_mb, growth, is_percent_growth, max_size
            FROM tempdb.sys.database_files WHERE type = 0 ORDER BY file_id
            """)
            files = fetch_all(cursor)
            cursor.execute("SELECT cpu_count FROM sys.dm_os_sys_info")
            cpu_count = cursor.fetchone()[0]
        file_count = len(files)
        sizes = [f['size_mb'] for f in files]
        equal_sizes = len(set(sizes)) == 1
        issues = []
        if file_count == 1: issues.append("Single TempDB file - high contention risk")
        if file_count < min(cpu_count, 8): issues.append(f"TempDB files ({file_count}) < CPU cores ({cpu_count}) - recommend {min(cpu_count, 8)} files")
        if not equal_sizes: issues.append("Unequal file sizes - proportional fill issues")
        return {'files': files, 'file_count': file_count, 'cpu_count': cpu_count,
                'equal_sizes': equal_sizes, 'issues': issues, 'issue_count': len(issues)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_temp_table_usage() -> Dict[str, Any]:
    """Get active temp tables (#temp, ##global)"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT t.name AS table_name, SUM(p.rows) AS row_count,
                   SUM(a.total_pages) * 8.0 / 1024 AS total_mb, SUM(a.used_pages) * 8.0 / 1024 AS used_mb
            FROM tempdb.sys.tables t
            INNER JOIN tempdb.sys.partitions p ON t.object_id = p.object_id
            INNER JOIN tempdb.sys.allocation_units a ON p.partition_id = a.container_id
            WHERE t.name LIKE '#%' OR t.name LIKE '##%'
            GROUP BY t.name ORDER BY total_mb DESC
            """)
            results = fetch_all(cursor)
        return {'temp_tables': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_version_store_usage() -> Dict[str, Any]:
    """Get version store size (row versioning, snapshot isolation)"""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
            SELECT SUM(version_store_reserved_page_count) * 8.0 / 1024 AS version_store_mb,
                   SUM(user_objects_alloc_page_count) * 8.0 / 1024 AS user_objects_mb,
                   SUM(internal_objects_alloc_page_count) * 8.0 / 1024 AS internal_objects_mb
            FROM tempdb.sys.dm_db_file_space_usage
            """)
            row = cursor.fetchone()
        if row:
            return {'version_store_mb': round(row[0], 2), 'user_objects_mb': round(row[1], 2),
                    'internal_objects_mb': round(row[2], 2), 'total_mb': round(sum(row), 2)}
        return {'error': 'No version store data'}
    except Exception as e:
        return {'error': str(e)}


@tool
def validate_tempdb_configuration() -> Dict[str, Any]:
    """Check TempDB configuration against best practices"""
    try:
        config_result = check_tempdb_file_configuration()
        if 'error' in config_result: return config_result
        recommendations = []
        file_count = config_result['file_count']
        cpu_count = config_result['cpu_count']
        optimal_files = min(cpu_count, 8)
        if file_count < optimal_files:
            recommendations.append({'category': 'File Count', 'issue': f'Only {file_count} files, recommend {optimal_files}',
                                     'action': f'Add {optimal_files - file_count} more TempDB files'})
        if not config_result['equal_sizes']:
            recommendations.append({'category': 'File Sizing', 'issue': 'Unequal file sizes', 'action': 'Resize all TempDB files to equal size'})
        percent_growth_files = [f for f in config_result['files'] if f['is_percent_growth']]
        if percent_growth_files:
            recommendations.append({'category': 'Growth Settings', 'issue': f'{len(percent_growth_files)} files using percent growth',
                                     'action': 'Change to fixed MB growth (e.g., 512 MB)'})
        return {'best_practices_met': len(recommendations) == 0, 'recommendations': recommendations, 'recommendation_count': len(recommendations)}
    except Exception as e:
        return {'error': str(e)}


@tool
def analyze_tempdb_bottleneck() -> Dict[str, Any]:
    """Comprehensive TempDB bottleneck analysis"""
    try:
        results = {}
        size_result = get_tempdb_size()
        results['size_analysis'] = size_result
        if 'usage_percent' in size_result and size_result['usage_percent'] > 80:
            results['space_warning'] = f"TempDB {size_result['usage_percent']}% full"
        contention_result = get_tempdb_contention()
        results['contention_analysis'] = contention_result
        io_result = get_tempdb_io_stats()
        results['io_analysis'] = io_result
        config_result = validate_tempdb_configuration()
        results['configuration_analysis'] = config_result
        bottlenecks = []
        if 'space_warning' in results: bottlenecks.append('SPACE_EXHAUSTION')
        if contention_result.get('contention_detected'): bottlenecks.append('LATCH_CONTENTION')
        if not config_result.get('best_practices_met'): bottlenecks.append('CONFIGURATION_ISSUES')
        results['primary_bottlenecks'] = bottlenecks
        results['bottleneck_count'] = len(bottlenecks)
        return results
    except Exception as e:
        return {'error': str(e)}


# ===== SNS =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    return send_notification(subject, message, severity, agent_name="Data Lifecycle Agent")
