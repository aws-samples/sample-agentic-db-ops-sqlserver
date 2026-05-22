import os

DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
DB_SECRET_ID = os.getenv('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
AWS_REGION = os.getenv('AWS_REGION_NAME', os.getenv('AWS_REGION', 'us-east-1'))
SNS_TOPIC_NAME = os.getenv('SNS_TOPIC_NAME', 'sqlserver-database-alerts')
