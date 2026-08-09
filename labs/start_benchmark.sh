# Updated: 2026-03-15
#!/bin/bash

# SQL Server Benchmark Script - DBOpsLab Setup & Workload
# Runs SQL setup files then executes stored procedures continuously

# Get database credentials from Secrets Manager
SECRET_ID="${DB_SECRET_ID:-dbops-infra-sqlserver-secret}"
REGION="${AWS_REGION:-us-east-1}"

echo "Retrieving database credentials..."
SECRET=$(aws secretsmanager get-secret-value --secret-id $SECRET_ID --region $REGION --query SecretString --output text)

DB_HOST=$(echo $SECRET | jq -r .host)
DB_USER=$(echo $SECRET | jq -r .username)
DB_PASS=$(echo $SECRET | jq -r .password)
DB_PORT=$(echo $SECRET | jq -r .port)

# Duration in minutes (default 4320 = 3 days)
DURATION=${1:-4320}
END_TIME=$(($(date +%s) + DURATION * 60))

echo "Starting SQL Server DBOpsLab setup and workload..."
echo "Host: $DB_HOST"
echo "Duration: $DURATION minutes"
echo "End time: $(date -d @$END_TIME)"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if database already exists and has data
echo "Checking if DBOpsLab database exists..."
DB_EXISTS=$(python3 -c "
import pymssql
try:
    conn = pymssql.connect(server='$DB_HOST', user='$DB_USER', password='$DB_PASS', port=$DB_PORT, database='DBOpsLab')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM Customers')
    count = cursor.fetchone()[0]
    conn.close()
    print('yes' if count > 0 else 'no')
except:
    print('no')
" 2>/dev/null)

if [ "$DB_EXISTS" = "yes" ]; then
    echo "DBOpsLab database already exists with data. Skipping setup..."
else
    echo "Running database setup (01_setup_and_populate.sql)..."
    python3 $SCRIPT_DIR/load_generator/run_sql_file.py $SCRIPT_DIR/load_generator/01_setup_and_populate.sql

    echo "Creating stored procedures (02_create_high_cpu_procedure.sql)..."
    python3 $SCRIPT_DIR/load_generator/run_sql_file.py $SCRIPT_DIR/load_generator/02_create_high_cpu_procedure.sql
fi

# Create workload script that calls stored procedures
cat > /tmp/sp_workload.py << 'PYEOF'
import pymssql
import random
import time
import os

host = os.environ['DB_HOST']
user = os.environ['DB_USER']
password = os.environ['DB_PASS']
port = int(os.environ['DB_PORT'])
end_time = int(os.environ['END_TIME'])

print(f"Starting stored procedure workload... will run until {time.ctime(end_time)}")

conn = pymssql.connect(server=host, user=user, password=password, port=port, database='DBOpsLab')
cursor = conn.cursor()

stored_procedures = [
    'sp_CustomerOrderSummary',
    'sp_ProductSalesReport',
    'sp_OrderAnalysisByYear',
    'sp_CustomerPurchaseHistory',
    'sp_ProductInventoryMatrix',
    'sp_MonthlyOrderReport'
]

iteration = 0
while time.time() < end_time:
    try:
        sp_name = random.choice(stored_procedures)
        print(f"Executing {sp_name}...")
        cursor.execute(f"EXEC {sp_name}")
        
        # Fetch all results
        while cursor.nextset():
            pass
        
        iteration += 1
        if iteration % 10 == 0:
            print(f"Completed {iteration} stored procedure calls...")
        
        # Sleep between calls
        time.sleep(random.uniform(2, 5))
        
    except Exception as e:
        print(f"Error executing {sp_name}: {e}")
        time.sleep(10)

cursor.close()
conn.close()
print("Workload completed!")
PYEOF

# Make script executable and run multiple concurrent workload processes
chmod +x /tmp/sp_workload.py
export DB_HOST DB_USER DB_PASS DB_PORT END_TIME

# Start 8 concurrent workload processes
for i in {1..8}; do
  python3 /tmp/sp_workload.py &
done

echo "DBOpsLab workload started with 8 concurrent processes"
