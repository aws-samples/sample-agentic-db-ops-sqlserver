# Updated: 2026-07-31
"""
Setup SNS Approval Workflow Infrastructure
==========================================
Creates:
1. DynamoDB table for approval requests
2. Lambda function for handling approve/reject clicks
3. API Gateway with /approve and /reject routes
4. SNS topic for sending approval emails

Usage:
    python setup_approval_workflow.py

After setup, set environment variable:
    export APPROVAL_API_URL=<api-gateway-url>
"""

import boto3
import json
import os
import time
import zipfile
import io

AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
STACK_PREFIX = 'dbops-approval'

iam_client = boto3.client('iam', region_name=AWS_REGION)
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
lambda_client = boto3.client('lambda', region_name=AWS_REGION)
apigateway_client = boto3.client('apigatewayv2', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)


def create_dynamodb_table():
    """Create DynamoDB table for approval requests"""
    table_name = f'{STACK_PREFIX}-requests'
    
    try:
        dynamodb_client.describe_table(TableName=table_name)
        print(f"  Table {table_name} already exists")
        return table_name
    except dynamodb_client.exceptions.ResourceNotFoundException:
        pass

    dynamodb_client.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': 'request_id', 'KeyType': 'HASH'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'request_id', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    # Wait for table to be active
    waiter = dynamodb_client.get_waiter('table_exists')
    waiter.wait(TableName=table_name)

    # Enable TTL separately
    dynamodb_client.update_time_to_live(
        TableName=table_name,
        TimeToLiveSpecification={
            'Enabled': True,
            'AttributeName': 'ttl'
        }
    )
    print(f"  ✅ DynamoDB table created: {table_name}")
    return table_name


def create_lambda_role():
    """Create IAM role for the approval Lambda"""
    role_name = f'{STACK_PREFIX}-lambda-role'
    
    try:
        response = iam_client.get_role(RoleName=role_name)
        print(f"  Role {role_name} already exists")
        return response['Role']['Arn']
    except iam_client.exceptions.NoSuchEntityException:
        pass

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    response = iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description='Role for DB Operations approval workflow Lambda'
    )
    role_arn = response['Role']['Arn']

    # Attach policies
    policies = [
        'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
        'arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess'
    ]
    for policy in policies:
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)

    # Wait for role propagation
    time.sleep(10)
    print(f"  ✅ IAM role created: {role_name}")
    return role_arn


def create_lambda_function(role_arn, table_name):
    """Create Lambda function that handles approve/reject"""
    function_name = f'{STACK_PREFIX}-handler'

    # Lambda code
    lambda_code = """
import json
import boto3
import os
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def handler(event, context):
    # Get parameters from query string
    params = event.get('queryStringParameters', {}) or {}
    request_id = params.get('id', '')
    token = params.get('token', '')
    confirm = params.get('confirm', '')

    # Determine action from path
    path = event.get('rawPath', '')
    if '/approve' in path:
        status = 'approved'
        color = '#10b981'
        icon = '&#10004;'
        title = 'APPROVED'
        action_verb = 'Approve'
        message = 'The action has been approved and will be executed by the database agent.'
    elif '/reject' in path:
        status = 'rejected'
        color = '#ef4444'
        icon = '&#10008;'
        title = 'REJECTED'
        action_verb = 'Reject'
        message = 'The action has been rejected. No changes will be made to the database.'
    else:
        return {'statusCode': 400, 'body': 'Invalid path'}

    if not request_id:
        return {'statusCode': 400, 'body': 'Missing request ID'}

    # Confirmation page to prevent link prefetching from auto-approving
    if not confirm:
        confirm_url = f"{path}?id={request_id}&token={token}&confirm=true"
        html = f'''<html>
        <head><title>DB Operations - Confirm {action_verb}</title></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                     display: flex; justify-content: center; align-items: center; min-height: 100vh;
                     margin: 0; background: #f8fafc;">
            <div style="text-align: center; padding: 48px; background: white; border-radius: 16px;
                        box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 520px;">
                <div style="font-size: 48px; margin-bottom: 16px;">&#9889;</div>
                <h1 style="color: #1e293b; margin: 0 0 8px; font-size: 24px;">Confirm {action_verb}</h1>
                <p style="color: #64748b; margin: 0 0 24px; font-size: 16px;">Are you sure you want to {action_verb.lower()} this action?</p>
                <div style="margin-bottom: 16px;">
                    <span style="color: #64748b; font-size: 13px;">Request ID: </span>
                    <span style="color: #1e293b; font-size: 13px; font-family: monospace;">{request_id}</span>
                </div>
                <a href="{confirm_url}" style="display: inline-block; background: {color}; color: white; padding: 14px 36px;
                   border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 15px;
                   box-shadow: 0 2px 8px rgba(0,0,0,0.15);">
                  Yes, {action_verb} this action
                </a>
                <p style="color: #94a3b8; font-size: 12px; margin-top: 24px;">
                    Autonomous DB Operations &bull; Actions Agent
                </p>
            </div>
        </body></html>'''
        return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': html}

    # Update DynamoDB with token validation
    try:
        table.update_item(
            Key={'request_id': request_id},
            UpdateExpression='SET #s = :status, decided_at = :ts',
            ConditionExpression='attribute_exists(request_id) AND #s = :pending AND #t = :token',
            ExpressionAttributeNames={'#s': 'status', '#t': 'token'},
            ExpressionAttributeValues={
                ':status': status,
                ':ts': datetime.now(timezone.utc).isoformat(),
                ':pending': 'pending',
                ':token': token
            }
        )
    except Exception as e:
        html = '''<html>
        <head><title>DB Operations</title></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                     display: flex; justify-content: center; align-items: center; min-height: 100vh;
                     margin: 0; background: #f8fafc;">
            <div style="text-align: center; padding: 40px; background: white; border-radius: 16px;
                        box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 480px;">
                <div style="font-size: 48px; margin-bottom: 16px;">&#9888;</div>
                <h2 style="color: #f59e0b; margin: 0 0 12px;">Already Processed</h2>
                <p style="color: #64748b;">This request has already been processed or has expired.</p>
            </div>
        </body></html>'''
        return {'statusCode': 200, 'headers': {'Content-Type': 'text/html'}, 'body': html}

    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

    html = f'''<html>
    <head><title>DB Operations - {title}</title></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                 display: flex; justify-content: center; align-items: center; min-height: 100vh;
                 margin: 0; background: #f8fafc;">
        <div style="text-align: center; padding: 48px; background: white; border-radius: 16px;
                    box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 520px;">
            <div style="width: 80px; height: 80px; border-radius: 50%; background: {color}15;
                        display: flex; align-items: center; justify-content: center; margin: 0 auto 24px;
                        border: 3px solid {color};">
                <span style="font-size: 36px; color: {color};">{icon}</span>
            </div>
            <h1 style="color: #1e293b; margin: 0 0 8px; font-size: 24px;">Action {title}</h1>
            <p style="color: #64748b; margin: 0 0 24px; font-size: 16px;">{message}</p>
            <div style="background: #f1f5f9; border-radius: 8px; padding: 16px; text-align: left;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="color: #64748b; font-size: 13px;">Request ID</span>
                    <span style="color: #1e293b; font-size: 13px; font-family: monospace;">{request_id}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                    <span style="color: #64748b; font-size: 13px;">Status</span>
                    <span style="color: {color}; font-size: 13px; font-weight: 600;">{status.upper()}</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #64748b; font-size: 13px;">Timestamp</span>
                    <span style="color: #1e293b; font-size: 13px;">{timestamp}</span>
                </div>
            </div>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 24px;">
                Autonomous DB Operations &bull; Actions Agent
            </p>
        </div>
    </body></html>'''

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html
    }
"""

    # Package as zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('lambda_function.py', lambda_code)
    zip_buffer.seek(0)

    try:
        lambda_client.get_function(FunctionName=function_name)
        # Update existing
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_buffer.read()
        )
        print(f"  Lambda {function_name} updated")
        response = lambda_client.get_function(FunctionName=function_name)
        return response['Configuration']['FunctionArn']
    except lambda_client.exceptions.ResourceNotFoundException:
        pass

    response = lambda_client.create_function(
        FunctionName=function_name,
        Runtime='python3.12',
        Role=role_arn,
        Handler='lambda_function.handler',
        Code={'ZipFile': zip_buffer.read()},
        Environment={
            'Variables': {
                'TABLE_NAME': table_name
            }
        },
        Timeout=10
    )

    # Wait for function to be active
    time.sleep(5)
    print(f"  ✅ Lambda function created: {function_name}")
    return response['FunctionArn']


def create_api_gateway(lambda_arn):
    """Create HTTP API Gateway with /approve and /reject routes"""
    api_name = f'{STACK_PREFIX}-api'

    # Check if exists
    apis = apigateway_client.get_apis()
    for api in apis.get('Items', []):
        if api['Name'] == api_name:
            api_id = api['ApiId']
            api_endpoint = api['ApiEndpoint']
            print(f"  API {api_name} already exists: {api_endpoint}")

            # Verify $default stage exists; create if missing
            try:
                apigateway_client.get_stage(ApiId=api_id, StageName='$default')
            except apigateway_client.exceptions.NotFoundException:
                apigateway_client.create_stage(
                    ApiId=api_id,
                    StageName='$default',
                    AutoDeploy=True
                )
                print(f"  ✅ Created missing $default stage for {api_name}")

            # Verify Lambda permission exists
            function_name = f'{STACK_PREFIX}-handler'
            account_id = boto3.client('sts').get_caller_identity()['Account']
            try:
                lambda_client.add_permission(
                    FunctionName=function_name,
                    StatementId=f'apigateway-invoke-{api_id}',
                    Action='lambda:InvokeFunction',
                    Principal='apigateway.amazonaws.com',
                    SourceArn=f'arn:aws:execute-api:{AWS_REGION}:{account_id}:{api_id}/*/*'
                )
                print(f"  ✅ Added missing Lambda invoke permission")
            except lambda_client.exceptions.ResourceConflictException:
                pass  # Permission already exists

            return api_endpoint

    # Create HTTP API
    api_response = apigateway_client.create_api(
        Name=api_name,
        ProtocolType='HTTP',
        Description='DB Operations approval workflow API'
    )
    api_id = api_response['ApiId']
    api_endpoint = api_response['ApiEndpoint']

    # Create Lambda integration
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    integration_response = apigateway_client.create_integration(
        ApiId=api_id,
        IntegrationType='AWS_PROXY',
        IntegrationUri=lambda_arn,
        PayloadFormatVersion='2.0'
    )
    integration_id = integration_response['IntegrationId']

    # Create routes
    for route in ['GET /approve', 'GET /reject']:
        apigateway_client.create_route(
            ApiId=api_id,
            RouteKey=route,
            Target=f'integrations/{integration_id}'
        )

    # Create default stage with auto-deploy
    apigateway_client.create_stage(
        ApiId=api_id,
        StageName='$default',
        AutoDeploy=True
    )

    # Grant API Gateway permission to invoke Lambda
    function_name = f'{STACK_PREFIX}-handler'
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=f'apigateway-invoke-{api_id}',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=f'arn:aws:execute-api:{AWS_REGION}:{account_id}:{api_id}/*/*'
        )
    except lambda_client.exceptions.ResourceConflictException:
        pass  # Permission already exists

    print(f"  ✅ API Gateway created: {api_endpoint}")
    return api_endpoint


def create_sns_topic():
    """Create SNS topic for approval notifications"""
    topic_name = f'{STACK_PREFIX}-notifications'
    
    response = sns_client.create_topic(Name=topic_name)
    topic_arn = response['TopicArn']
    print(f"  ✅ SNS topic: {topic_arn}")
    return topic_arn


def main():
    print("=" * 60)
    print("Setting up Approval Workflow Infrastructure")
    print("=" * 60)
    print()

    print("[1/5] Creating DynamoDB table...")
    table_name = create_dynamodb_table()

    print("[2/5] Creating IAM role...")
    role_arn = create_lambda_role()

    print("[3/5] Creating Lambda function...")
    lambda_arn = create_lambda_function(role_arn, table_name)

    print("[4/5] Creating API Gateway...")
    api_url = create_api_gateway(lambda_arn)

    print("[5/5] Creating SNS topic...")
    topic_arn = create_sns_topic()

    # SES email setup
    print()
    email = input("[6/6] Enter your email address for approval notifications: ").strip()
    if email:
        ses_client = boto3.client('ses', region_name=AWS_REGION)
        try:
            ses_client.verify_email_identity(EmailAddress=email)
            print(f"  ✅ SES verification email sent to {email}")
            print(f"     Check your inbox and click the verification link.")
        except Exception as e:
            print(f"  ⚠️  SES verification failed: {e}")
    else:
        email = 'your-email@example.com'
        print("  ⚠️  No email provided. Set SES_SENDER_EMAIL and SES_RECIPIENT_EMAIL manually.")

    # Save config
    config = {
        'api_url': api_url,
        'table_name': table_name,
        'topic_arn': topic_arn,
        'lambda_arn': lambda_arn,
        'ses_email': email,
        'region': AWS_REGION
    }
    with open('approval_workflow_config.json', 'w') as f:
        json.dump(config, f, indent=2)

    # Write env file and append to bashrc
    env_file = os.path.expanduser('~/.dbops_env')
    bashrc_path = os.path.expanduser('~/.bashrc')

    # Read existing env file or create new
    existing = {}
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('export '):
                    key = line.split('=')[0].replace('export ', '')
                    existing[key] = line.strip()

    # Update with new values
    existing['APPROVAL_API_URL'] = f'export APPROVAL_API_URL={api_url}'
    existing['APPROVAL_TABLE_NAME'] = f'export APPROVAL_TABLE_NAME={table_name}'
    existing['APPROVAL_SNS_TOPIC_ARN'] = f'export APPROVAL_SNS_TOPIC_ARN={topic_arn}'
    existing['SES_SENDER_EMAIL'] = f'export SES_SENDER_EMAIL={email}'
    existing['SES_RECIPIENT_EMAIL'] = f'export SES_RECIPIENT_EMAIL={email}'

    # Write env file
    with open(env_file, 'w') as f:
        f.write('# DBOps environment variables (auto-generated)\n')
        for line in existing.values():
            f.write(line + '\n')

    # Ensure bashrc sources the env file
    source_line = '[ -f ~/.dbops_env ] && source ~/.dbops_env'
    with open(bashrc_path, 'r') as f:
        bashrc_content = f.read()
    if source_line not in bashrc_content:
        with open(bashrc_path, 'a') as f:
            f.write(f'\n{source_line}\n')

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  ✅ Approval Workflow Ready                       ║")
    print("  ╠══════════════════════════════════════════════════╣")
    print(f"  ║  APPROVAL_API_URL:    {api_url[:25]+'...' if len(api_url)>25 else api_url:<28}║")
    print(f"  ║  APPROVAL_TABLE:      {table_name:<28}║")
    print(f"  ║  SES_SENDER_EMAIL:    {email:<28}║")
    print(f"  ║  SES_RECIPIENT_EMAIL: {email:<28}║")
    print("  ╚══════════════════════════════════════════════════╝")
    print(f"\n  Run: source ~/.dbops_env")


if __name__ == '__main__':
    main()
