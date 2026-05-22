import boto3
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from strands import tool
from config.settings import DB_INSTANCE_ID, AWS_REGION, SNS_TOPIC_NAME
from tools.shared_utils import send_notification


def get_pi_client():
    return boto3.client('pi', region_name=AWS_REGION)


def get_rds_resource_id():
    rds_client = boto3.client('rds', region_name=AWS_REGION)
    db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    return db_response['DBInstances'][0]['DbiResourceId']


def calculate_period(minutes_back):
    if minutes_back <= 1440:
        return 60
    elif minutes_back <= 4320:
        return 300
    else:
        return 600


# ===== DATABASE INSIGHTS TOOLS =====

@tool
def get_database_load(hours_back: int = 24) -> Dict[str, Any]:
    """Get database load timeline from Database Insights with trend analysis. Use 1-minute granularity for ≤24 hours, 1-hour for longer periods."""
    try:
        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)
        period = 60 if hours_back <= 24 else 3600

        response = pi_client.get_resource_metrics(
            ServiceType='RDS', Identifier=resource_id,
            MetricQueries=[{'Metric': 'db.load.avg'}],
            StartTime=start_time, EndTime=end_time, PeriodInSeconds=period
        )

        if response['MetricList']:
            datapoints = response['MetricList'][0].get('DataPoints', [])
            if datapoints:
                loads = [dp['Value'] for dp in datapoints]
                sorted_dps = sorted(datapoints, key=lambda x: x['Timestamp'])
                peak_dp = max(datapoints, key=lambda x: x['Value'])
                return {
                    'period_seconds': period, 'datapoint_count': len(datapoints),
                    'min_load': round(min(loads), 2), 'max_load': round(max(loads), 2),
                    'avg_load': round(sum(loads) / len(loads), 2),
                    'current_load': round(sorted_dps[-1]['Value'], 2),
                    'peak_timestamp': peak_dp['Timestamp'].isoformat(),
                    'peak_value': round(peak_dp['Value'], 2),
                    'timeline': [{'timestamp': dp['Timestamp'].isoformat(), 'load': round(dp['Value'], 2)} for dp in sorted_dps]
                }
        return {'error': 'No data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_extended_database_load(hours_back: int = 72) -> Dict[str, Any]:
    """Get extended database load with statistics. Checks instance creation time and only returns available data."""
    try:
        rds_client = boto3.client('rds', region_name=AWS_REGION)
        db_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        instance_create_time = db_response['DBInstances'][0]['InstanceCreateTime']

        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        all_data = []
        end_time = datetime.now(timezone.utc)
        requested_start_time = end_time - timedelta(hours=hours_back)
        start_time = max(requested_start_time, instance_create_time)
        actual_hours_back = (end_time - start_time).total_seconds() / 3600
        current_start = start_time

        while current_start < end_time:
            current_end = min(current_start + timedelta(hours=24), end_time)
            response = pi_client.get_resource_metrics(
                ServiceType='RDS', Identifier=resource_id,
                StartTime=current_start, EndTime=current_end, PeriodInSeconds=3600,
                MetricQueries=[{'Metric': 'db.load.avg'}]
            )
            if response['MetricList'] and response['MetricList'][0].get('DataPoints'):
                all_data.extend(response['MetricList'][0]['DataPoints'])
            current_start = current_end

        if all_data:
            loads = [dp['Value'] for dp in all_data]
            first_datapoint = min(dp['Timestamp'] for dp in all_data)
            last_datapoint = max(dp['Timestamp'] for dp in all_data)
            return {
                'hours_requested': hours_back,
                'actual_hours_available': round(actual_hours_back, 1),
                'instance_created': instance_create_time.isoformat(),
                'data_range_start': first_datapoint.isoformat(),
                'data_range_end': last_datapoint.isoformat(),
                'datapoint_count': len(all_data),
                'min_load': round(min(loads), 2), 'max_load': round(max(loads), 2),
                'avg_load': round(sum(loads) / len(loads), 2),
                'note': f'Instance only exists for {round(actual_hours_back, 1)} hours' if actual_hours_back < hours_back else None
            }
        return {'error': 'No data available', 'instance_created': instance_create_time.isoformat()}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_wait_events(hours_back: int = 24) -> Dict[str, Any]:
    """Get wait event types breakdown with timeline showing when wait patterns changed (CPU, IO, Log, Other, etc.)"""
    try:
        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        response = pi_client.get_resource_metrics(
            ServiceType='RDS', Identifier=resource_id,
            MetricQueries=[{'Metric': 'db.load.avg', 'GroupBy': {'Group': 'db.wait_event_type', 'Limit': 10}}],
            StartTime=start_time, EndTime=end_time, PeriodInSeconds=3600
        )

        wait_events = {}
        timeline = {}
        if response.get('MetricList'):
            for metric in response['MetricList']:
                wait_type = metric.get('Key', {}).get('Dimensions', {}).get('db.wait_event_type.name', 'Total')
                if metric.get('DataPoints'):
                    datapoints = sorted(metric['DataPoints'], key=lambda x: x['Timestamp'])
                    values = [dp['Value'] for dp in datapoints]
                    latest = datapoints[-1]
                    wait_events[wait_type] = {
                        'current': round(latest['Value'], 2), 'avg': round(sum(values) / len(values), 2),
                        'max': round(max(values), 2), 'min': round(min(values), 2)
                    }
                    for dp in datapoints:
                        ts = dp['Timestamp'].isoformat()
                        if ts not in timeline:
                            timeline[ts] = {}
                        timeline[ts][wait_type] = round(dp['Value'], 2)

        return {'wait_events_summary': wait_events, 'timeline': timeline} if wait_events else {'error': 'No wait event data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_top_sql(hours_back: int = 24, limit: int = 5) -> Dict[str, Any]:
    """Get top SQL queries with actual query text (not tokenized)"""
    try:
        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        response = pi_client.get_resource_metrics(
            ServiceType='RDS', Identifier=resource_id,
            MetricQueries=[{'Metric': 'db.load.avg', 'GroupBy': {'Group': 'db.sql', 'Limit': limit}}],
            StartTime=start_time, EndTime=end_time, PeriodInSeconds=3600
        )

        queries = []
        if response.get('MetricList'):
            for metric in response['MetricList']:
                statement = metric.get('Key', {}).get('Dimensions', {}).get('db.sql.statement', 'N/A')
                if metric.get('DataPoints') and statement not in ['N/A', 'Total']:
                    latest = metric['DataPoints'][-1]
                    queries.append({'load': round(latest['Value'], 2), 'query': statement[:500]})

        return {'queries': queries} if queries else {'error': 'No SQL query data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_users(hours_back: int = 24) -> Dict[str, Any]:
    """Get database users and their load contribution"""
    try:
        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        response = pi_client.get_resource_metrics(
            ServiceType='RDS', Identifier=resource_id,
            MetricQueries=[{'Metric': 'db.load.avg', 'GroupBy': {'Group': 'db.user', 'Limit': 10}}],
            StartTime=start_time, EndTime=end_time, PeriodInSeconds=3600
        )

        users = {}
        if response.get('MetricList'):
            for metric in response['MetricList']:
                user_name = metric.get('Key', {}).get('Dimensions', {}).get('db.user.name', 'Total')
                if metric.get('DataPoints'):
                    users[user_name] = round(metric['DataPoints'][-1]['Value'], 2)

        return users if users else {'error': 'No user data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_applications(hours_back: int = 24) -> Dict[str, Any]:
    """Get applications and their load contribution"""
    try:
        pi_client = get_pi_client()
        resource_id = get_rds_resource_id()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours_back)

        response = pi_client.get_resource_metrics(
            ServiceType='RDS', Identifier=resource_id,
            MetricQueries=[{'Metric': 'db.load.avg', 'GroupBy': {'Group': 'db.application', 'Limit': 10}}],
            StartTime=start_time, EndTime=end_time, PeriodInSeconds=3600
        )

        apps = {}
        if response.get('MetricList'):
            for metric in response['MetricList']:
                app_name = metric.get('Key', {}).get('Dimensions', {}).get('db.application.name', 'Total')
                if metric.get('DataPoints'):
                    apps[app_name] = round(metric['DataPoints'][-1]['Value'], 2)

        return apps if apps else {'error': 'No application data available'}
    except Exception as e:
        return {'error': str(e)}


# ===== CLOUDWATCH TOOLS =====

@tool
def get_database_connections(minutes_back: int = 4320) -> Dict[str, Any]:
    """Get database connection count timeline from CloudWatch with trend analysis. Supports up to 7 days."""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(minutes_back)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='DatabaseConnections',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=minutes_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum']
        )
        if response['Datapoints']:
            sorted_dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            avgs = [dp['Average'] for dp in sorted_dps]
            peak_dp = max(sorted_dps, key=lambda x: x['Maximum'])
            latest = sorted_dps[-1]
            return {
                'period_seconds': period, 'datapoint_count': len(sorted_dps),
                'current_avg': round(latest['Average'], 0), 'current_max': round(latest['Maximum'], 0),
                'overall_avg': round(sum(avgs) / len(avgs), 0),
                'peak_connections': round(peak_dp['Maximum'], 0),
                'peak_timestamp': peak_dp['Timestamp'].isoformat(),
                'min_connections': round(min(avgs), 0),
                'timeline': [{'timestamp': dp['Timestamp'].isoformat(), 'avg': round(dp['Average'], 0), 'max': round(dp['Maximum'], 0)} for dp in sorted_dps]
            }
        return {'error': 'No connection data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_cpu_utilization(minutes_back: int = 1440) -> Dict[str, Any]:
    """Get CPU utilization timeline from CloudWatch with trend analysis. Supports up to 7 days."""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(minutes_back)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='CPUUtilization',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=minutes_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Maximum']
        )
        if response['Datapoints']:
            sorted_dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            avgs = [dp['Average'] for dp in sorted_dps]
            peak_dp = max(sorted_dps, key=lambda x: x['Maximum'])
            latest = sorted_dps[-1]
            return {
                'period_seconds': period, 'datapoint_count': len(sorted_dps),
                'current_avg': round(latest['Average'], 2), 'current_max': round(latest['Maximum'], 2),
                'min_avg': round(min(avgs), 2), 'max_avg': round(max(avgs), 2),
                'overall_avg': round(sum(avgs) / len(avgs), 2),
                'peak_timestamp': peak_dp['Timestamp'].isoformat(),
                'peak_value': round(peak_dp['Maximum'], 2),
                'timeline': [{'timestamp': dp['Timestamp'].isoformat(), 'avg': round(dp['Average'], 2), 'max': round(dp['Maximum'], 2)} for dp in sorted_dps]
            }
        return {'error': 'No CPU data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_free_storage(minutes_back: int = 4320) -> Dict[str, Any]:
    """Get free storage space timeline from CloudWatch with growth trend analysis. Supports up to 7 days."""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(minutes_back)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='FreeStorageSpace',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=minutes_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average']
        )
        if response['Datapoints']:
            sorted_dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            free_gb = [dp['Average'] / (1024**3) for dp in sorted_dps]
            first_free = free_gb[0]
            last_free = free_gb[-1]
            return {
                'period_seconds': period, 'datapoint_count': len(sorted_dps),
                'current_free_gb': round(last_free, 2), 'initial_free_gb': round(first_free, 2),
                'storage_consumed_gb': round(first_free - last_free, 2),
                'min_free_gb': round(min(free_gb), 2), 'max_free_gb': round(max(free_gb), 2),
                'timeline': [{'timestamp': dp['Timestamp'].isoformat(), 'free_gb': round(dp['Average'] / (1024**3), 2)} for dp in sorted_dps]
            }
        return {'error': 'No storage data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_read_write_latency() -> Dict[str, Any]:
    """Get read and write latency from CloudWatch"""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        latencies = {}
        for metric_name in ['ReadLatency', 'WriteLatency']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(hours=72),
                EndTime=datetime.now(timezone.utc), Period=calculate_period(72*60), Statistics=['Average', 'Maximum']
            )
            if response['Datapoints']:
                latest = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])[-1]
                latencies[metric_name] = {'average_ms': round(latest['Average'] * 1000, 2), 'maximum_ms': round(latest['Maximum'] * 1000, 2)}
        return latencies if latencies else {'error': 'No latency data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_iops() -> Dict[str, Any]:
    """Get read and write IOPS from CloudWatch"""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        iops = {}
        for metric_name in ['ReadIOPS', 'WriteIOPS']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(hours=72),
                EndTime=datetime.now(timezone.utc), Period=calculate_period(72*60), Statistics=['Average', 'Maximum']
            )
            if response['Datapoints']:
                latest = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])[-1]
                iops[metric_name] = {'average': round(latest['Average'], 2), 'maximum': round(latest['Maximum'], 2)}
        return iops if iops else {'error': 'No IOPS data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_network_throughput() -> Dict[str, Any]:
    """Get network throughput from CloudWatch"""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        network = {}
        for metric_name in ['NetworkReceiveThroughput', 'NetworkTransmitThroughput']:
            response = cw.get_metric_statistics(
                Namespace='AWS/RDS', MetricName=metric_name,
                Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
                StartTime=datetime.now(timezone.utc) - timedelta(hours=72),
                EndTime=datetime.now(timezone.utc), Period=calculate_period(72*60), Statistics=['Average', 'Maximum']
            )
            if response['Datapoints']:
                latest = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])[-1]
                network[metric_name] = {'average_mbps': round(latest['Average'] / (1024**2), 2), 'maximum_mbps': round(latest['Maximum'] / (1024**2), 2)}
        return network if network else {'error': 'No network data available'}
    except Exception as e:
        return {'error': str(e)}


@tool
def get_freeable_memory(minutes_back: int = 4320) -> Dict[str, Any]:
    """Get freeable memory timeline from CloudWatch with trend analysis. Supports up to 7 days."""
    try:
        cw = boto3.client('cloudwatch', region_name=AWS_REGION)
        period = calculate_period(minutes_back)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='FreeableMemory',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': DB_INSTANCE_ID}],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=minutes_back),
            EndTime=datetime.now(timezone.utc), Period=period, Statistics=['Average', 'Minimum']
        )
        if response['Datapoints']:
            sorted_dps = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            avgs_gb = [dp['Average'] / (1024**3) for dp in sorted_dps]
            mins_gb = [dp['Minimum'] / (1024**3) for dp in sorted_dps]
            latest = sorted_dps[-1]
            return {
                'period_seconds': period, 'datapoint_count': len(sorted_dps),
                'current_avg_gb': round(latest['Average'] / (1024**3), 2),
                'current_min_gb': round(latest['Minimum'] / (1024**3), 2),
                'overall_avg_gb': round(sum(avgs_gb) / len(avgs_gb), 2),
                'lowest_memory_gb': round(min(mins_gb), 2), 'highest_memory_gb': round(max(avgs_gb), 2),
                'timeline': [{'timestamp': dp['Timestamp'].isoformat(), 'avg_gb': round(dp['Average'] / (1024**3), 2), 'min_gb': round(dp['Minimum'] / (1024**3), 2)} for dp in sorted_dps]
            }
        return {'error': 'No memory data available'}
    except Exception as e:
        return {'error': str(e)}


# ===== SNS =====

@tool
def send_email_notification(subject: str, message: str, severity: str = "INFO") -> Dict[str, Any]:
    """Send an email notification via SNS. Severity: INFO, WARNING, CRITICAL"""
    return send_notification(subject, message, severity, agent_name="Database Health Agent")
