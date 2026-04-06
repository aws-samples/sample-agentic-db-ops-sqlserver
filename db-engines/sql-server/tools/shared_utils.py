"""Shared utilities for SQL Server tool modules.

Centralizes database connection, query execution, and SNS notification
logic to eliminate duplication across tool files.
"""
import boto3
import pymssql
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any
from config.settings import DB_INSTANCE_ID, DB_SECRET_ID, AWS_REGION, SNS_TOPIC_NAME


def get_db_connection():
    """Get a pymssql connection to the RDS SQL Server instance."""
    rds_client = boto3.client('rds', region_name=AWS_REGION)
    rds_response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    endpoint = rds_response['DBInstances'][0]['Endpoint']
    host = endpoint['Address']
    port = endpoint['Port']

    secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
    secret = secrets_client.get_secret_value(SecretId=DB_SECRET_ID)
    creds = json.loads(secret['SecretString'])
    return pymssql.connect(
        server=host, user=creds['username'],
        password=creds['password'], port=port, database='master'
    )


@contextmanager
def db_cursor():
    """Context manager that yields a cursor and auto-closes connection."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.close()


def fetch_all(cursor) -> list[dict]:
    """Fetch all rows from cursor as a list of dicts."""
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def send_notification(subject: str, message: str, severity: str = "INFO", agent_name: str = "Agent") -> Dict[str, Any]:
    """Send an email notification via SNS."""
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
        formatted_message = (
            f"\nSQL SERVER {agent_name.upper()} ALERT\n"
            f"{'=' * (len(agent_name) + 24)}\n"
            f"Timestamp: {timestamp}\n"
            f"Severity: {severity}\n"
            f"Subject: {subject}\n\n"
            f"{message}\n\n"
            f"---\nSent by AgentCore {agent_name}\n"
        )
        sns_subject = f"[{severity}] {subject}"[:100]
        resp = sns_client.publish(TopicArn=topic_arn, Subject=sns_subject, Message=formatted_message)
        return {'status': 'success', 'message_id': resp.get('MessageId'), 'severity': severity}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}
