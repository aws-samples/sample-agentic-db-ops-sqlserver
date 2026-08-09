# Updated: 2026-03-15
#!/usr/bin/env python3
import boto3
import json
import pymssql
import os

AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')

print("1. Fetching secret from Secrets Manager...")
secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
secret = secrets_client.get_secret_value(SecretId=DB_SECRET_ID)
creds = json.loads(secret['SecretString'])

print(f"2. Secret retrieved successfully")
print(f"   Host: {creds['host']}")
print(f"   Port: {creds['port']}")
print(f"   User: {creds['username']}")

print("3. Attempting database connection...")
conn = pymssql.connect(
    server=creds['host'],
    user=creds['username'],
    password=creds['password'],
    port=creds['port'],
    database='master'
)

print("4. Connection successful!")

cursor = conn.cursor()
cursor.execute("SELECT @@VERSION")
version = cursor.fetchone()[0]
print(f"5. SQL Server version: {version[:100]}...")

cursor.execute("SELECT actual_state_desc FROM sys.database_query_store_options")
row = cursor.fetchone()
print(f"6. Query Store status: {row[0] if row else 'Not configured'}")

cursor.close()
conn.close()
print("7. Test complete!")
