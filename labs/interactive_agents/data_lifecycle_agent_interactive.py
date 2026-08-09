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
        raise Exception(f"Error connecting to database: {str(e)}")

def calculate_period(minutes_back):
    """Calculate CloudWatch period to stay under 1440 datapoint limit"""
    if minutes_back <= 1440:
        return 60
    elif minutes_back <= 4320:
        return 300
    else:
        return 600

def get_instance_age_hours():
    """Get the age of the RDS instance in hours"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        instance_create_time = response['DBInstances'][0]['InstanceCreateTime']
        age = datetime.now(timezone.utc) - instance_create_time
        return age.total_seconds() / 3600
    except Exception as e:
        return None

# Define the AI model
model = BedrockModel(
    model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
    region_name=AWS_REGION,
    temperature=0.0
)

# ===== CLOUDWATCH STORAGE TOOLS =====

@tool
def get_storage_metrics(days_back: int = 7) -> Dict[str, Any]:
    """Get storage usage and growth trends from CloudWatch with timeline breakdown"""
    try:
        # Check instance age
        instance_age_hours = get_instance_age_hours()
        if instance_age_hours and instance_age_hours < days_back * 24:
            days_back = max(1, int(instance_age_hours / 24))
        
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        metrics = {}
        for metric_name in ['FreeStorageSpace', 'AllocatedStorage']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc),
                Period=period,
                Statistics=['Average', 'Minimum', 'Maximum']
            )
            
            if response['Datapoints']:
                datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                values_gb = [dp['Average'] / (1024**3) for dp in datapoints]
                
                metrics[metric_name] = {
                    'current_gb': round(values_gb[-1], 2),
                    'initial_gb': round(values_gb[0], 2),
                    'change_gb': round(values_gb[-1] - values_gb[0], 2),
                    'min_gb': round(min(values_gb), 2),
                    'max_gb': round(max(values_gb), 2),
                    'avg_gb': round(sum(values_gb) / len(values_gb), 2),
                    'datapoint_count': len(datapoints),
                    'period_seconds': period
                }
        
        return metrics if metrics else {'error': 'No storage data available'}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_iops_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get IOPS trends from CloudWatch with timeline breakdown"""
    try:
        # Check instance age
        instance_age_hours = get_instance_age_hours()
        if instance_age_hours and instance_age_hours < days_back * 24:
            days_back = max(1, int(instance_age_hours / 24))
        
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        iops = {}
        for metric_name in ['ReadIOPS', 'WriteIOPS']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc),
                Period=period,
                Statistics=['Average', 'Maximum', 'Minimum']
            )
            
            if response['Datapoints']:
                datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avg_values = [dp['Average'] for dp in datapoints]
                max_values = [dp['Maximum'] for dp in datapoints]
                
                iops[metric_name] = {
                    'current_avg': round(avg_values[-1], 2),
                    'current_max': round(max_values[-1], 2),
                    'period_avg': round(sum(avg_values) / len(avg_values), 2),
                    'period_max': round(max(max_values), 2),
                    'period_min': round(min(avg_values), 2),
                    'datapoint_count': len(datapoints),
                    'period_seconds': period
                }
        
        return iops if iops else {'error': 'No IOPS data available'}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_throughput_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get read/write throughput trends from CloudWatch"""
    try:
        # Check instance age
        instance_age_hours = get_instance_age_hours()
        if instance_age_hours and instance_age_hours < days_back * 24:
            days_back = max(1, int(instance_age_hours / 24))
        
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        throughput = {}
        for metric_name in ['ReadThroughput', 'WriteThroughput']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc),
                Period=period,
                Statistics=['Average', 'Maximum', 'Minimum']
            )
            
            if response['Datapoints']:
                datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avg_values = [dp['Average'] / (1024**2) for dp in datapoints]  # Convert to MB/s
                max_values = [dp['Maximum'] / (1024**2) for dp in datapoints]
                
                throughput[metric_name] = {
                    'current_avg_mbps': round(avg_values[-1], 2),
                    'current_max_mbps': round(max_values[-1], 2),
                    'period_avg_mbps': round(sum(avg_values) / len(avg_values), 2),
                    'period_max_mbps': round(max(max_values), 2),
                    'period_min_mbps': round(min(avg_values), 2),
                    'datapoint_count': len(datapoints)
                }
        
        return throughput if throughput else {'error': 'No throughput data available'}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_latency_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get read/write latency trends from CloudWatch"""
    try:
        # Check instance age
        instance_age_hours = get_instance_age_hours()
        if instance_age_hours and instance_age_hours < days_back * 24:
            days_back = max(1, int(instance_age_hours / 24))
        
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        latency = {}
        for metric_name in ['ReadLatency', 'WriteLatency']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS',
                MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
                EndTime=datetime.now(timezone.utc),
                Period=period,
                Statistics=['Average', 'Maximum', 'Minimum']
            )
            
            if response['Datapoints']:
                datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
                avg_values = [dp['Average'] * 1000 for dp in datapoints]  # Convert to ms
                max_values = [dp['Maximum'] * 1000 for dp in datapoints]
                
                latency[metric_name] = {
                    'current_avg_ms': round(avg_values[-1], 2),
                    'current_max_ms': round(max_values[-1], 2),
                    'period_avg_ms': round(sum(avg_values) / len(avg_values), 2),
                    'period_max_ms': round(max(max_values), 2),
                    'period_min_ms': round(min(avg_values), 2),
                    'datapoint_count': len(datapoints)
                }
        
        return latency if latency else {'error': 'No latency data available'}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_queue_depth_trends(days_back: int = 7) -> Dict[str, Any]:
    """Get disk queue depth trends from CloudWatch (bottleneck indicator)"""
    try:
        # Check instance age
        instance_age_hours = get_instance_age_hours()
        if instance_age_hours and instance_age_hours < days_back * 24:
            days_back = max(1, int(instance_age_hours / 24))
        
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName='DiskQueueDepth',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
            EndTime=datetime.now(timezone.utc),
            Period=period,
            Statistics=['Average', 'Maximum', 'Minimum']
        )
        
        if response['Datapoints']:
            datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            avg_values = [dp['Average'] for dp in datapoints]
            max_values = [dp['Maximum'] for dp in datapoints]
            
            return {
                'current_avg': round(avg_values[-1], 2),
                'current_max': round(max_values[-1], 2),
                'period_avg': round(sum(avg_values) / len(avg_values), 2),
                'period_max': round(max(max_values), 2),
                'period_min': round(min(avg_values), 2),
                'datapoint_count': len(datapoints),
                'bottleneck_warning': max(max_values) > 1.0
            }
        return {'error': 'No queue depth data available'}
    except Exception as e:
        return {'error': str(e)}

# ===== DMV STORAGE TOOLS =====

@tool
def get_database_size() -> Dict[str, Any]:
    """Get total database size"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            DB_NAME(database_id) AS database_name,
            SUM(size * 8.0 / 1024) AS size_mb
        FROM sys.master_files
        WHERE database_id > 4
        GROUP BY database_id
        ORDER BY size_mb DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'databases': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_table_sizes() -> Dict[str, Any]:
    """Get table sizes sorted by space used"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 20
            t.NAME AS table_name,
            s.Name AS schema_name,
            p.rows AS row_count,
            SUM(a.total_pages) * 8 / 1024 AS total_space_mb,
            SUM(a.used_pages) * 8 / 1024 AS used_space_mb,
            (SUM(a.total_pages) - SUM(a.used_pages)) * 8 / 1024 AS unused_space_mb
        FROM sys.tables t
        INNER JOIN sys.indexes i ON t.OBJECT_ID = i.object_id
        INNER JOIN sys.partitions p ON i.object_id = p.OBJECT_ID AND i.index_id = p.index_id
        INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
        LEFT OUTER JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE t.NAME NOT LIKE 'dt%' 
        AND t.is_ms_shipped = 0
        AND i.OBJECT_ID > 255
        GROUP BY t.Name, s.Name, p.Rows
        ORDER BY total_space_mb DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'tables': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_index_sizes() -> Dict[str, Any]:
    """Get index sizes to identify large indexes"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 20
            OBJECT_NAME(i.object_id) AS table_name,
            i.name AS index_name,
            i.type_desc AS index_type,
            SUM(s.used_page_count) * 8 / 1024 AS index_size_mb
        FROM sys.dm_db_partition_stats s
        INNER JOIN sys.indexes i ON s.object_id = i.object_id AND s.index_id = i.index_id
        WHERE OBJECTPROPERTY(i.object_id, 'IsUserTable') = 1
        GROUP BY i.object_id, i.name, i.type_desc
        ORDER BY index_size_mb DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def identify_old_data(table_name: str, date_column: str, days_old: int = 365) -> Dict[str, Any]:
    """Identify old data candidates for archival"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = f"""
        SELECT 
            COUNT(*) as old_record_count,
            MIN({date_column}) as oldest_date,
            MAX({date_column}) as newest_old_date
        FROM {table_name}
        WHERE {date_column} < DATEADD(day, -{days_old}, GETDATE())
        """
        
        cursor.execute(query)
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if result:
            return {
                'table_name': table_name,
                'old_record_count': result[0],
                'oldest_date': result[1].isoformat() if result[1] else None,
                'newest_old_date': result[2].isoformat() if result[2] else None,
                'days_threshold': days_old
            }
        return {'error': 'No data found'}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_fragmentation_status() -> Dict[str, Any]:
    """Get index fragmentation status"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 20
            OBJECT_NAME(ips.object_id) AS table_name,
            i.name AS index_name,
            ips.index_type_desc,
            ips.avg_fragmentation_in_percent,
            ips.page_count
        FROM sys.dm_db_index_physical_stats(DB_ID(), NULL, NULL, NULL, 'LIMITED') ips
        INNER JOIN sys.indexes i ON ips.object_id = i.object_id AND ips.index_id = i.index_id
        WHERE ips.avg_fragmentation_in_percent > 10
        AND ips.page_count > 1000
        ORDER BY ips.avg_fragmentation_in_percent DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        return {'fragmented_indexes': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

# ===== RDS API TOOLS =====

@tool
def check_backup_status() -> Dict[str, Any]:
    """Check backup status and retention"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        
        # Get DB instance backup info
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = db_response['DBInstances'][0]
        
        # Get recent snapshots
        snapshot_response = rds_client.describe_db_snapshots(
            DBInstanceIdentifier=DB_INSTANCE_ID,
            MaxRecords=20
        )
        
        snapshots = []
        for snapshot in snapshot_response.get('DBSnapshots', []):
            snapshots.append({
                'snapshot_id': snapshot['DBSnapshotIdentifier'],
                'snapshot_create_time': snapshot['SnapshotCreateTime'].isoformat(),
                'status': snapshot['Status'],
                'type': snapshot['SnapshotType'],
                'allocated_storage': snapshot['AllocatedStorage']
            })
        
        return {
            'backup_retention_period': db_instance['BackupRetentionPeriod'],
            'preferred_backup_window': db_instance['PreferredBackupWindow'],
            'latest_restorable_time': db_instance.get('LatestRestorableTime', 'N/A').isoformat() if db_instance.get('LatestRestorableTime') != 'N/A' else 'N/A',
            'recent_snapshots': snapshots,
            'snapshot_count': len(snapshots)
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def analyze_storage_growth(days_back: int = 30) -> Dict[str, Any]:
    """Analyze storage growth trends"""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        minutes_back = days_back * 24 * 60
        period = calculate_period(minutes_back)
        
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName='FreeStorageSpace',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(days=days_back),
            EndTime=datetime.now(timezone.utc),
            Period=period,
            Statistics=['Average']
        )
        
        if response['Datapoints']:
            datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            first_free = datapoints[0]['Average'] / (1024**3)
            latest_free = datapoints[-1]['Average'] / (1024**3)
            used_growth = first_free - latest_free
            
            # Calculate daily growth rate
            days_elapsed = (datapoints[-1]['Timestamp'] - datapoints[0]['Timestamp']).days
            daily_growth = used_growth / days_elapsed if days_elapsed > 0 else 0
            
            # Project when storage will be full (assuming linear growth)
            days_until_full = latest_free / daily_growth if daily_growth > 0 else float('inf')
            
            return {
                'days_analyzed': days_back,
                'initial_free_gb': round(first_free, 2),
                'current_free_gb': round(latest_free, 2),
                'growth_gb': round(used_growth, 2),
                'daily_growth_gb': round(daily_growth, 2),
                'days_until_full': round(days_until_full, 0) if days_until_full != float('inf') else 'N/A'
            }
        return {'error': 'No storage data available'}
    except Exception as e:
        return {'error': str(e)}

# ===== STORAGE CONFIGURATION & RECOMMENDATIONS =====

@tool
def get_storage_configuration() -> Dict[str, Any]:
    """Get RDS storage configuration (type, IOPS, throughput)"""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db_instance = response['DBInstances'][0]
        
        config = {
            'storage_type': db_instance['StorageType'],
            'allocated_storage_gb': db_instance['AllocatedStorage'],
            'max_allocated_storage_gb': db_instance.get('MaxAllocatedStorage'),
            'storage_encrypted': db_instance['StorageEncrypted']
        }
        
        # Add IOPS if provisioned
        if 'Iops' in db_instance:
            config['provisioned_iops'] = db_instance['Iops']
        
        # Add throughput for gp3
        if 'StorageThroughput' in db_instance:
            config['provisioned_throughput_mbps'] = db_instance['StorageThroughput']
        
        return config
    except Exception as e:
        return {'error': str(e)}

@tool
def recommend_storage_upgrade() -> Dict[str, Any]:
    """Analyze metrics and recommend storage type upgrade"""
    try:
        # Get current configuration
        config_result = get_storage_configuration()
        if 'error' in config_result:
            return config_result
        
        storage_type = config_result['storage_type']
        
        # Get recent performance metrics
        iops_result = get_iops_trends(days_back=1)
        latency_result = get_latency_trends(days_back=1)
        queue_result = get_queue_depth_trends(days_back=1)
        
        recommendations = []
        
        # Check for high latency
        if 'ReadLatency' in latency_result and latency_result['ReadLatency']['period_avg_ms'] > 20:
            recommendations.append({
                'issue': 'High read latency',
                'current_avg_ms': latency_result['ReadLatency']['period_avg_ms'],
                'recommendation': 'Consider upgrading to io2 for lower latency'
            })
        
        # Check for high queue depth
        if 'bottleneck_warning' in queue_result and queue_result['bottleneck_warning']:
            recommendations.append({
                'issue': 'High disk queue depth',
                'current_max': queue_result['period_max'],
                'recommendation': 'Storage cannot keep up with demand - upgrade to higher IOPS'
            })
        
        # gp2 to gp3 recommendation (cost optimization)
        if storage_type == 'gp2':
            recommendations.append({
                'issue': 'Using gp2 storage',
                'recommendation': 'Upgrade to gp3 for better price/performance (20% cost savings, better baseline performance)'
            })
        
        # Check if hitting IOPS limits
        if storage_type in ['gp2', 'gp3']:
            read_iops = iops_result.get('ReadIOPS', {}).get('period_max', 0)
            write_iops = iops_result.get('WriteIOPS', {}).get('period_max', 0)
            total_iops = read_iops + write_iops
            
            # gp2 limit: 3 IOPS per GB, max 16000
            # gp3 baseline: 3000 IOPS, max 16000
            if storage_type == 'gp2':
                allocated_gb = config_result['allocated_storage_gb']
                gp2_limit = min(allocated_gb * 3, 16000)
                if total_iops > gp2_limit * 0.8:
                    recommendations.append({
                        'issue': 'Approaching gp2 IOPS limit',
                        'current_iops': round(total_iops, 0),
                        'gp2_limit': gp2_limit,
                        'recommendation': 'Upgrade to gp3 with provisioned IOPS or io2'
                    })
        
        return {
            'current_storage_type': storage_type,
            'recommendations': recommendations,
            'recommendation_count': len(recommendations)
        }
    except Exception as e:
        return {'error': str(e)}

# ===== TEMPDB CRITICAL TOOLS =====

@tool
def get_tempdb_size() -> Dict[str, Any]:
    """Get TempDB current size, used space, and free space per file"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            name AS file_name,
            physical_name,
            size * 8.0 / 1024 AS size_mb,
            FILEPROPERTY(name, 'SpaceUsed') * 8.0 / 1024 AS used_mb,
            (size - FILEPROPERTY(name, 'SpaceUsed')) * 8.0 / 1024 AS free_mb,
            growth,
            is_percent_growth
        FROM tempdb.sys.database_files
        ORDER BY file_id
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        total_size = sum(r['size_mb'] for r in results)
        total_used = sum(r['used_mb'] for r in results)
        
        return {
            'files': results,
            'file_count': len(results),
            'total_size_mb': round(total_size, 2),
            'total_used_mb': round(total_used, 2),
            'total_free_mb': round(total_size - total_used, 2),
            'usage_percent': round((total_used / total_size * 100) if total_size > 0 else 0, 2)
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def get_tempdb_space_usage_by_session() -> Dict[str, Any]:
    """Get TempDB space usage by session"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 10
            s.session_id,
            s.login_name,
            s.host_name,
            s.program_name,
            SUM(u.user_objects_alloc_page_count) * 8.0 / 1024 AS user_objects_mb,
            SUM(u.internal_objects_alloc_page_count) * 8.0 / 1024 AS internal_objects_mb,
            SUM(u.user_objects_alloc_page_count + u.internal_objects_alloc_page_count) * 8.0 / 1024 AS total_mb
        FROM sys.dm_db_session_space_usage u
        INNER JOIN sys.dm_exec_sessions s ON u.session_id = s.session_id
        WHERE (u.user_objects_alloc_page_count + u.internal_objects_alloc_page_count) > 0
        GROUP BY s.session_id, s.login_name, s.host_name, s.program_name
        ORDER BY total_mb DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'sessions': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_tempdb_space_usage_by_query() -> Dict[str, Any]:
    """Get TempDB space usage by currently running queries"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT TOP 10
            r.session_id,
            r.status,
            r.command,
            SUBSTRING(st.text, (r.statement_start_offset/2)+1,
                ((CASE r.statement_end_offset
                    WHEN -1 THEN DATALENGTH(st.text)
                    ELSE r.statement_end_offset
                END - r.statement_start_offset)/2) + 1) AS query_text,
            t.user_objects_alloc_page_count * 8.0 / 1024 AS user_objects_mb,
            t.internal_objects_alloc_page_count * 8.0 / 1024 AS internal_objects_mb,
            (t.user_objects_alloc_page_count + t.internal_objects_alloc_page_count) * 8.0 / 1024 AS total_mb
        FROM sys.dm_exec_requests r
        CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
        INNER JOIN sys.dm_db_task_space_usage t ON r.session_id = t.session_id AND r.request_id = t.request_id
        WHERE (t.user_objects_alloc_page_count + t.internal_objects_alloc_page_count) > 0
        ORDER BY total_mb DESC
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
def get_tempdb_contention() -> Dict[str, Any]:
    """Get TempDB PFS/SGAM/GAM page latch contention"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            wait_type,
            waiting_tasks_count,
            wait_time_ms,
            max_wait_time_ms,
            signal_wait_time_ms
        FROM sys.dm_os_wait_stats
        WHERE wait_type LIKE 'PAGELATCH%'
        AND wait_time_ms > 0
        ORDER BY wait_time_ms DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        has_contention = any(r['wait_time_ms'] > 10000 for r in results)
        
        return {
            'latch_waits': results,
            'contention_detected': has_contention,
            'count': len(results)
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def get_tempdb_io_stats() -> Dict[str, Any]:
    """Get TempDB file I/O latency and stalls"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            mf.name AS file_name,
            mf.physical_name,
            vfs.num_of_reads,
            vfs.num_of_writes,
            vfs.num_of_bytes_read / 1024 / 1024 AS mb_read,
            vfs.num_of_bytes_written / 1024 / 1024 AS mb_written,
            vfs.io_stall_read_ms,
            vfs.io_stall_write_ms,
            CASE WHEN vfs.num_of_reads > 0 
                THEN vfs.io_stall_read_ms / vfs.num_of_reads 
                ELSE 0 END AS avg_read_latency_ms,
            CASE WHEN vfs.num_of_writes > 0 
                THEN vfs.io_stall_write_ms / vfs.num_of_writes 
                ELSE 0 END AS avg_write_latency_ms
        FROM sys.dm_io_virtual_file_stats(DB_ID('tempdb'), NULL) vfs
        INNER JOIN tempdb.sys.master_files mf ON vfs.file_id = mf.file_id AND vfs.database_id = mf.database_id
        ORDER BY vfs.io_stall_read_ms + vfs.io_stall_write_ms DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'file_io_stats': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def check_tempdb_file_configuration() -> Dict[str, Any]:
    """Check TempDB file configuration (count, sizes, growth)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get file configuration
        query = """
        SELECT 
            name,
            size * 8.0 / 1024 AS size_mb,
            growth,
            is_percent_growth,
            max_size
        FROM tempdb.sys.database_files
        WHERE type = 0  -- Data files only
        ORDER BY file_id
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        files = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Get CPU count for comparison
        cursor.execute("SELECT cpu_count FROM sys.dm_os_sys_info")
        cpu_count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Check for issues
        file_count = len(files)
        sizes = [f['size_mb'] for f in files]
        equal_sizes = len(set(sizes)) == 1
        
        issues = []
        if file_count == 1:
            issues.append("Single TempDB file - high contention risk")
        if file_count < min(cpu_count, 8):
            issues.append(f"TempDB files ({file_count}) < CPU cores ({cpu_count}) - recommend {min(cpu_count, 8)} files")
        if not equal_sizes:
            issues.append("Unequal file sizes - proportional fill issues")
        
        return {
            'files': files,
            'file_count': file_count,
            'cpu_count': cpu_count,
            'equal_sizes': equal_sizes,
            'issues': issues,
            'issue_count': len(issues)
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def get_temp_table_usage() -> Dict[str, Any]:
    """Get active temp tables (#temp, ##global)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            t.name AS table_name,
            SUM(p.rows) AS row_count,
            SUM(a.total_pages) * 8.0 / 1024 AS total_mb,
            SUM(a.used_pages) * 8.0 / 1024 AS used_mb
        FROM tempdb.sys.tables t
        INNER JOIN tempdb.sys.partitions p ON t.object_id = p.object_id
        INNER JOIN tempdb.sys.allocation_units a ON p.partition_id = a.container_id
        WHERE t.name LIKE '#%' OR t.name LIKE '##%'
        GROUP BY t.name
        ORDER BY total_mb DESC
        """
        
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return {'temp_tables': results, 'count': len(results)}
    except Exception as e:
        return {'error': str(e)}

@tool
def get_version_store_usage() -> Dict[str, Any]:
    """Get version store size (row versioning, snapshot isolation)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT 
            SUM(version_store_reserved_page_count) * 8.0 / 1024 AS version_store_mb,
            SUM(user_objects_alloc_page_count) * 8.0 / 1024 AS user_objects_mb,
            SUM(internal_objects_alloc_page_count) * 8.0 / 1024 AS internal_objects_mb
        FROM tempdb.sys.dm_db_file_space_usage
        """
        
        cursor.execute(query)
        row = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if row:
            return {
                'version_store_mb': round(row[0], 2),
                'user_objects_mb': round(row[1], 2),
                'internal_objects_mb': round(row[2], 2),
                'total_mb': round(sum(row), 2)
            }
        return {'error': 'No version store data'}
    except Exception as e:
        return {'error': str(e)}

@tool
def validate_tempdb_configuration() -> Dict[str, Any]:
    """Check TempDB configuration against best practices"""
    try:
        config_result = check_tempdb_file_configuration()
        if 'error' in config_result:
            return config_result
        
        recommendations = []
        
        # Check file count
        file_count = config_result['file_count']
        cpu_count = config_result['cpu_count']
        optimal_files = min(cpu_count, 8)
        
        if file_count < optimal_files:
            recommendations.append({
                'category': 'File Count',
                'issue': f'Only {file_count} files, recommend {optimal_files}',
                'action': f'Add {optimal_files - file_count} more TempDB files'
            })
        
        # Check equal sizing
        if not config_result['equal_sizes']:
            recommendations.append({
                'category': 'File Sizing',
                'issue': 'Unequal file sizes',
                'action': 'Resize all TempDB files to equal size'
            })
        
        # Check for percent growth
        files = config_result['files']
        percent_growth_files = [f for f in files if f['is_percent_growth']]
        if percent_growth_files:
            recommendations.append({
                'category': 'Growth Settings',
                'issue': f'{len(percent_growth_files)} files using percent growth',
                'action': 'Change to fixed MB growth (e.g., 512 MB)'
            })
        
        return {
            'best_practices_met': len(recommendations) == 0,
            'recommendations': recommendations,
            'recommendation_count': len(recommendations)
        }
    except Exception as e:
        return {'error': str(e)}

@tool
def analyze_tempdb_bottleneck() -> Dict[str, Any]:
    """Comprehensive TempDB bottleneck analysis"""
    try:
        results = {}
        
        # Get size and usage
        size_result = get_tempdb_size()
        results['size_analysis'] = size_result
        
        # Check for space issues
        if 'usage_percent' in size_result and size_result['usage_percent'] > 80:
            results['space_warning'] = f"TempDB {size_result['usage_percent']}% full"
        
        # Check contention
        contention_result = get_tempdb_contention()
        results['contention_analysis'] = contention_result
        
        # Check I/O performance
        io_result = get_tempdb_io_stats()
        results['io_analysis'] = io_result
        
        # Check configuration
        config_result = validate_tempdb_configuration()
        results['configuration_analysis'] = config_result
        
        # Determine primary bottleneck
        bottlenecks = []
        if 'space_warning' in results:
            bottlenecks.append('SPACE_EXHAUSTION')
        if contention_result.get('contention_detected'):
            bottlenecks.append('LATCH_CONTENTION')
        if not config_result.get('best_practices_met'):
            bottlenecks.append('CONFIGURATION_ISSUES')
        
        results['primary_bottlenecks'] = bottlenecks
        results['bottleneck_count'] = len(bottlenecks)
        
        return results
    except Exception as e:
        return {'error': str(e)}

# ===== SNS NOTIFICATION TOOL =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
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
SQL SERVER DATA LIFECYCLE ALERT
================================
Timestamp: {timestamp}
Severity: {severity}
Subject: {subject}

{message}

---
Sent by AgentCore Data Lifecycle Agent
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

system_prompt = """You are a TOOL EXECUTOR for RDS SQL Server storage, TempDB, and backup data.

Your ONLY job is to call the requested tools and return their raw output. You are not a reasoner.

RULES:
1. Call the tools relevant to the request and return their raw results verbatim.
2. Do NOT classify, rank, or assign severity/priority (no Critical/High/Medium).
3. Do NOT summarize, interpret, diagnose, or recommend upgrades. No prose, no conclusions.
4. Do NOT send email notifications.
5. If a tool returns no data or an error, return that fact as-is. Never invent values.

The Supervisor does ALL reasoning. You only execute tools and hand back data.

Available tools:

**CloudWatch Storage Metrics (with timeline analysis):**
- get_storage_metrics: Storage usage and growth trends (enhanced with min/max/avg)
- get_iops_trends: IOPS trends (enhanced with timeline breakdown)
- get_throughput_trends: Read/write throughput trends
- get_latency_trends: Read/write latency trends
- get_queue_depth_trends: Disk queue depth (bottleneck indicator)
- analyze_storage_growth: Storage growth rate and days until full

**Storage Configuration & Recommendations:**
- get_storage_configuration: Current storage type (gp2/gp3/io1/io2), IOPS, throughput
- recommend_storage_upgrade: Analyze metrics and suggest gp3/io2 upgrades

**DMV Storage Analysis:**
- get_database_size: Total database sizes
- get_table_sizes: Top 20 tables by space
- get_index_sizes: Top 20 indexes by space
- identify_old_data: Find archival candidates by date
- get_fragmentation_status: Index fragmentation >10%

**TempDB Critical Analysis (12 tools):**
- get_tempdb_size: Current size, used/free space per file
- get_tempdb_space_usage_by_session: Which sessions consuming TempDB
- get_tempdb_space_usage_by_query: Which queries using TempDB
- get_tempdb_growth_history: Auto-growth events
- get_tempdb_contention: PFS/SGAM/GAM page latch contention
- get_tempdb_io_stats: TempDB file I/O latency and stalls
- check_tempdb_file_configuration: File count, sizes, growth settings
- get_temp_table_usage: Active temp tables (#temp, ##global)
- get_version_store_usage: Version store size (row versioning)
- validate_tempdb_configuration: Best practices check
- analyze_tempdb_bottleneck: Comprehensive root cause analysis

**Backup & Compliance:**
- check_backup_status: Backup retention, recent snapshots

**Alerting:**
- send_email_notification: Send lifecycle alerts

**Investigation workflow:**

1. **Storage Analysis**: Use get_storage_metrics and analyze_storage_growth for capacity planning
2. **Performance Bottlenecks**: Check get_latency_trends, get_queue_depth_trends, get_iops_trends
3. **Storage Optimization**: Use recommend_storage_upgrade for cost/performance improvements
4. **Space Management**: Use get_table_sizes, get_index_sizes to identify large objects
5. **TempDB Issues**: Use analyze_tempdb_bottleneck for comprehensive TempDB analysis
6. **Data Archival**: Use identify_old_data to find archival candidates
7. **Maintenance**: Check get_fragmentation_status for index maintenance needs
8. **Compliance**: Verify check_backup_status for backup compliance

Return the raw tool outputs for the checks performed (storage, performance, TempDB, backup). Do not classify, recommend upgrades, or format a report — the Supervisor interprets the data."""

agent = Agent(
    system_prompt=system_prompt,
    model=model,
    tools=[
        # CloudWatch Storage Metrics
        get_storage_metrics,
        get_iops_trends,
        get_throughput_trends,
        get_latency_trends,
        get_queue_depth_trends,
        analyze_storage_growth,
        # Storage Configuration
        get_storage_configuration,
        recommend_storage_upgrade,
        # DMV Storage Analysis
        get_database_size,
        get_table_sizes,
        get_index_sizes,
        identify_old_data,
        get_fragmentation_status,
        # TempDB Tools
        get_tempdb_size,
        get_tempdb_space_usage_by_session,
        get_tempdb_space_usage_by_query,
        get_tempdb_contention,
        get_tempdb_io_stats,
        check_tempdb_file_configuration,
        get_temp_table_usage,
        get_version_store_usage,
        validate_tempdb_configuration,
        analyze_tempdb_bottleneck,
        # Backup & Compliance
        check_backup_status,
        # Alerting
        send_email_notification
    ]
)

if __name__ == "__main__":
    print("Data Lifecycle Agent - Manage storage, TempDB, and data lifecycle.")
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
