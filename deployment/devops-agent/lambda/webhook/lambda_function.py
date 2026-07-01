"""Webhook Executor Lambda — bridges CloudWatch Alarms to AWS DevOps Agent.

When a CloudWatch Alarm enters ALARM state it directly invokes this Lambda.
The function retrieves webhook credentials from Secrets Manager, constructs
an HMAC-SHA256 signed payload, and POSTs it to the DevOps Agent webhook
endpoint to trigger an autonomous investigation.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request

import boto3


def get_webhook_credentials():
    """Retrieve webhook URL and secret from Secrets Manager."""
    secret_arn = os.environ["WEBHOOK_SECRET_ARN"]
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])
    return secret["webhookUrl"], secret["webhookSecret"]


def lambda_handler(event, context):
    print("Webhook Executor invoked")
    print(f"CloudWatch Alarm event: {json.dumps(event, default=str)}")

    webhook_url, webhook_secret = get_webhook_credentials()

    alarm_data = event.get("alarmData", {})
    alarm_name = alarm_data.get("alarmName", "Unknown")
    state = alarm_data.get("state", {})
    alarm_arn = event.get("alarmArn", "Unknown")
    region = event.get("region", os.environ.get("AWS_REGION", "us-east-1"))

    namespace = "AWS/RDS"
    metrics = alarm_data.get("configuration", {}).get("metrics", [])
    if metrics:
        namespace = metrics[0].get("metricStat", {}).get("metric", {}).get("namespace", "AWS/RDS")

    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    payload = {
        "eventType": "incident",
        "incidentId": f"alarm-{alarm_name}-{int(time.time())}",
        "action": "created",
        "priority": "HIGH" if state.get("value") == "ALARM" else "MEDIUM",
        "title": alarm_name,
        "description": (
            f'CloudWatch Alarm "{alarm_name}" entered {state.get("value", "ALARM")} state.\n\n'
            f'Reason: {state.get("reason", "No reason provided")}\n'
            f"Alarm ARN: {alarm_arn}\n"
            f"Region: {region}"
        ),
        "service": namespace,
        "timestamp": timestamp,
        "data": {
            "metadata": {
                "alarm_name": alarm_name,
                "alarm_arn": alarm_arn,
                "region": region,
                "state": state.get("value", "ALARM"),
                "reason": state.get("reason", ""),
            }
        },
    }

    payload_json = json.dumps(payload)

    signature_input = f"{timestamp}:{payload_json}"
    signature = hmac.new(
        webhook_secret.encode("utf-8"),
        signature_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "x-amzn-event-signature": signature_b64,
        "x-amzn-event-timestamp": timestamp,
    }

    print(f"Sending webhook request to DevOps Agent (payload size: {len(payload_json)})")

    req = urllib.request.Request(
        webhook_url,
        data=payload_json.encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            status = resp.status
            body = resp.read().decode("utf-8")
            print(f"Webhook response: status={status}, body={body}")
            return {"statusCode": status, "body": "Webhook invoked successfully"}
    except urllib.error.HTTPError as e:
        print(f"Webhook request failed: status={e.code}, body={e.read().decode('utf-8')}")
        raise
