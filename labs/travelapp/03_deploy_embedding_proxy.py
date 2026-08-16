#!/usr/bin/env python3
"""
Deploy the Bedrock Embedding Proxy (Lambda + API Gateway).
This creates the serverless translation layer that allows SQL Server
to call Bedrock via CREATE EXTERNAL MODEL + AI_GENERATE_EMBEDDINGS.

Usage:
    python3 03_deploy_embedding_proxy.py
"""
import boto3
import json
import os
import time
import zipfile
import tempfile

region = os.environ.get('AWS_REGION', 'us-west-2')
account_id = boto3.client('sts').get_caller_identity()['Account']

print("Deploying Bedrock Embedding Proxy...")
print(f"  Region: {region}")
print(f"  Account: {account_id}")

iam = boto3.client('iam')
lam = boto3.client('lambda', region_name=region)
apigw = boto3.client('apigateway', region_name=region)

# Step 1: Create IAM Role
ROLE_NAME = 'bedrock-embedding-lambda-role'
print("\n1. Creating IAM role...")
try:
    role = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
        })
    )
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName='BedrockAccess', PolicyDocument=json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": "*"},
            {"Effect": "Allow", "Action": ["logs:*"], "Resource": "*"}
        ]
    }))
    print(f"   Role created: {role['Role']['Arn']}")
    time.sleep(10)  # Wait for role propagation
except iam.exceptions.EntityAlreadyExistsException:
    print(f"   Role already exists")
    role = iam.get_role(RoleName=ROLE_NAME)

role_arn = f"arn:aws:iam::{account_id}:role/{ROLE_NAME}"

# Step 2: Create Lambda Function
FUNCTION_NAME = 'bedrock-embedding-proxy'
print("\n2. Creating Lambda function...")

lambda_code = '''
import json
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        input_text = body.get('input', body.get('inputText', ''))
        if isinstance(input_text, list):
            input_text = input_text[0]
        dimensions = body.get('dimensions', 1024)
        
        response = bedrock.invoke_model(
            modelId='amazon.titan-embed-text-v2:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({'inputText': input_text[:8000], 'dimensions': dimensions})
        )
        
        result = json.loads(response['body'].read())
        embedding = result['embedding']
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'object': 'list',
                'data': [{'object': 'embedding', 'embedding': embedding, 'index': 0}],
                'model': 'amazon.titan-embed-text-v2',
                'usage': {'prompt_tokens': len(input_text.split()), 'total_tokens': len(input_text.split())}
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': {'message': str(e), 'type': 'server_error'}})
        }
'''

# Create zip
with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
    zip_path = tmp.name
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('lambda_function.py', lambda_code)

with open(zip_path, 'rb') as f:
    zip_bytes = f.read()

try:
    lam.create_function(
        FunctionName=FUNCTION_NAME, Runtime='python3.12',
        Role=role_arn, Handler='lambda_function.lambda_handler',
        Code={'ZipFile': zip_bytes}, Timeout=30, MemorySize=256
    )
    print(f"   Function created: {FUNCTION_NAME}")
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
    lam.update_function_configuration(FunctionName=FUNCTION_NAME, Handler='lambda_function.lambda_handler')
    print(f"   Function updated: {FUNCTION_NAME}")

time.sleep(5)

# Step 3: Create API Gateway
print("\n3. Creating API Gateway...")
apis = apigw.get_rest_apis()['items']
existing = [a for a in apis if a['name'] == 'bedrock-embedding-api']

if existing:
    api_id = existing[0]['id']
    print(f"   API already exists: {api_id}")
else:
    api = apigw.create_rest_api(name='bedrock-embedding-api', endpointConfiguration={'types': ['REGIONAL']})
    api_id = api['id']
    print(f"   API created: {api_id}")

# Get root resource
resources = apigw.get_resources(restApiId=api_id)['items']
root_id = [r for r in resources if r['path'] == '/'][0]['id']

# Create /embed resource if not exists
embed_resources = [r for r in resources if r.get('pathPart') == 'embed']
if embed_resources:
    resource_id = embed_resources[0]['id']
else:
    resource = apigw.create_resource(restApiId=api_id, parentId=root_id, pathPart='embed')
    resource_id = resource['id']

# Create POST method
try:
    apigw.put_method(restApiId=api_id, resourceId=resource_id, httpMethod='POST', authorizationType='NONE')
except:
    pass

# Create Lambda integration
lambda_uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/arn:aws:lambda:{region}:{account_id}:function:{FUNCTION_NAME}/invocations"
try:
    apigw.put_integration(restApiId=api_id, resourceId=resource_id, httpMethod='POST', type='AWS_PROXY', integrationHttpMethod='POST', uri=lambda_uri)
except:
    pass

# Add Lambda permission
try:
    lam.add_permission(FunctionName=FUNCTION_NAME, StatementId='apigateway-invoke', Action='lambda:InvokeFunction', Principal='apigateway.amazonaws.com')
except:
    pass

# Deploy
apigw.create_deployment(restApiId=api_id, stageName='prod')

endpoint = f"https://{api_id}.execute-api.{region}.amazonaws.com/prod/embed"
print(f"\n   Endpoint: {endpoint}")

# Step 4: Save endpoint for SQL scripts
env_file = '/tmp/embedding_endpoint.txt'
with open(env_file, 'w') as f:
    f.write(endpoint)

print(f"\n{'='*60}")
print(f"DONE! Embedding proxy deployed.")
print(f"Endpoint: {endpoint}")
print(f"\nNext: python3.11 run_sql_file.py load_generator/04_register_model.sql")
print(f"{'='*60}")
