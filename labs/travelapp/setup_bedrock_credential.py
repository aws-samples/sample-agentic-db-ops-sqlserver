#!/usr/bin/env python3
"""
Generate a Bedrock API key and store it as a Database Scoped Credential in TravelAI.
No manual editing needed — runs end-to-end.

Usage:
    python3 setup_bedrock_credential.py
"""
import pymssql
import json
import boto3
import os

region = os.environ.get('AWS_REGION', 'us-west-2')
secret_id = os.environ.get('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')

print("1. Generating Bedrock API key...")
from aws_bedrock_token_generator import BedrockTokenGenerator
generator = BedrockTokenGenerator()
session = boto3.Session(region_name=region)
credentials = session.get_credentials().get_frozen_credentials()
api_key = generator.get_token(credentials, region)
print(f"   Key generated (length: {len(api_key)})")

print("2. Connecting to TravelAI...")
sm = boto3.client('secretsmanager', region_name=region)
creds = json.loads(sm.get_secret_value(SecretId=secret_id)['SecretString'])
conn = pymssql.connect(server=creds['host'], user=creds['username'], password=creds['password'], port=int(creds['port']), database='TravelAI')
conn.autocommit(True)
cur = conn.cursor()

print("3. Creating Master Key...")
cur.execute("IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##') CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'Str0ngP@ss2026!'")

print("4. Storing Bedrock credential...")
cur.execute("IF EXISTS (SELECT 1 FROM sys.database_scoped_credentials WHERE name = 'https://bedrock-runtime.us-west-2.amazonaws.com') DROP DATABASE SCOPED CREDENTIAL [https://bedrock-runtime.us-west-2.amazonaws.com]")

secret_json = json.dumps({"Authorization": f"Bearer {api_key}"})
cur.execute(f"""
CREATE DATABASE SCOPED CREDENTIAL [https://bedrock-runtime.{region}.amazonaws.com]
WITH IDENTITY = 'HTTPEndpointHeaders',
     SECRET = '{secret_json}'
""")

print("5. Verifying...")
cur.execute("SELECT name FROM sys.database_scoped_credentials")
cred_names = [r[0] for r in cur.fetchall()]
print(f"   Credentials: {cred_names}")

conn.close()
print("\nDONE! Bedrock credential stored in TravelAI.")
print("sp_invoke_external_rest_endpoint can now call Bedrock models.")
