# Updated: 2026-03-15
import boto3
import pymssql
import json
import sys
import os
import time

if len(sys.argv) < 2:
    print("Usage: python run_sql_file.py <sql_file>")
    sys.exit(1)

sql_file = sys.argv[1]

def resolve_region():
    # Prefer explicit env var, then boto3's own resolution (profile/config),
    # then the EC2 instance metadata region. Avoid hardcoding a region so the
    # script works in whatever region it is deployed to.
    region = os.getenv('AWS_REGION') or os.getenv('AWSREGION')
    if region:
        return region
    session_region = boto3.session.Session().region_name
    if session_region:
        return session_region
    try:
        import urllib.request
        token = urllib.request.urlopen(
            urllib.request.Request(
                'http://169.254.169.254/latest/api/token',
                headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'},
                method='PUT'),
            timeout=2).read().decode()
        return urllib.request.urlopen(
            urllib.request.Request(
                'http://169.254.169.254/latest/meta-data/placement/region',
                headers={'X-aws-ec2-metadata-token': token}),
            timeout=2).read().decode()
    except Exception:
        return 'us-west-2'

# Get credentials from AWS Secrets Manager
client = boto3.client('secretsmanager', region_name=resolve_region())
secret = client.get_secret_value(SecretId='dbops-infra-sqlserver-secret')
creds = json.loads(secret['SecretString'])

# Connect to SQL Server
conn = pymssql.connect(
    server=creds['host'],
    user=creds['username'],
    password=creds['password'],
    port=creds['port']
)

print(f"Executing {sql_file}...")
print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

# Read SQL file
with open(sql_file, 'r') as f:
    sql_content = f.read()

# Split by GO statements
batches = [batch.strip() for batch in sql_content.split('GO') if batch.strip()]

cursor = conn.cursor()
batch_num = 0

# Disable autocommit for better control
conn.autocommit(True)

for batch in batches:
    batch_num += 1
    try:
        cursor.execute(batch)
        # Fetch and print messages
        while cursor.nextset():
            pass
    except Exception as e:
        print(f"Error in batch {batch_num}: {e}")

cursor.close()
conn.close()

print(f"\nCompleted at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
