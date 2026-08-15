#!/bin/bash
# TravelHub Benchmark Script

SECRET_ID="${DB_SECRET_ID:-dbops-infra-sqlserver-secret}"
REGION="${AWS_REGION:-us-west-2}"

echo "Retrieving database credentials..."
SECRET=$(aws secretsmanager get-secret-value --secret-id $SECRET_ID --region $REGION --query SecretString --output text)

DB_HOST=$(echo $SECRET | jq -r .host)
DB_USER=$(echo $SECRET | jq -r .username)
DB_PASS=$(echo $SECRET | jq -r .password)
DB_PORT=$(echo $SECRET | jq -r .port)

DURATION=${1:-4320}
END_TIME=$(($(date +%s) + DURATION * 60))

echo "Starting TravelHub benchmark workload..."
echo "Host: $DB_HOST"
echo "Duration: $DURATION minutes"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if TravelHub database exists
echo "Checking if TravelHub database exists..."
DB_EXISTS=$(python3 -c "
import pymssql
try:
    conn = pymssql.connect(server='$DB_HOST', user='$DB_USER', password='$DB_PASS', port=$DB_PORT, database='TravelHub')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM Users')
    count = cursor.fetchone()[0]
    conn.close()
    print('yes' if count > 0 else 'no')
except:
    print('no')
" 2>/dev/null)

if [ "$DB_EXISTS" = "yes" ]; then
    echo "TravelHub database already exists with data. Skipping setup..."
else
    echo "Running schema setup (01_create_schema.sql)..."
    python3 $SCRIPT_DIR/run_sql_file.py $SCRIPT_DIR/load_generator/01_create_schema.sql

    echo "Populating data (02_populate_data.sql)..."
    python3 $SCRIPT_DIR/run_sql_file.py $SCRIPT_DIR/load_generator/02_populate_data.sql

    echo "Creating stored procedures (03_create_bad_procedures.sql)..."
    python3 $SCRIPT_DIR/run_sql_file.py $SCRIPT_DIR/load_generator/03_create_bad_procedures.sql
fi

# Create workload script
cat > /tmp/travelapp_workload.py << 'PYEOF'
import pymssql
import random
import time
import os

host = os.environ['DB_HOST']
user = os.environ['DB_USER']
password = os.environ['DB_PASS']
port = int(os.environ['DB_PORT'])
end_time = int(os.environ['END_TIME'])

conn = pymssql.connect(server=host, user=user, password=password, port=port, database='TravelHub')
cursor = conn.cursor()

stored_procedures = [
    'sp_MatchDestinationsByPreferences',
    'sp_SearchDestinationsByDescription',
    'sp_FilterDestinationsAdvanced',
    'sp_SearchFlightsByRoute',
    'sp_CheckAndBookAvailability'
]

# Parameters for each SP
def get_params(sp_name):
    if sp_name == 'sp_MatchDestinationsByPreferences':
        return str(random.randint(1, 1000))
    elif sp_name == 'sp_SearchDestinationsByDescription':
        terms = ['beach resort', 'eco-friendly diving', 'luxury spa', 'adventure hiking', 'family snorkeling']
        return f"'{random.choice(terms)}'"
    elif sp_name == 'sp_FilterDestinationsAdvanced':
        return f"{random.randint(50,200)}, {random.randint(300,800)}, {random.uniform(3.0,4.5):.1f}"
    elif sp_name == 'sp_SearchFlightsByRoute':
        origins = ['JFK', 'LAX', 'ORD', 'ATL', 'DFW', 'SFO', 'MIA']
        dests = ['CDG', 'NRT', 'LHR', 'SYD', 'DXB', 'SIN', 'FCO']
        return f"'{random.choice(origins)}', '{random.choice(dests)}'"
    elif sp_name == 'sp_CheckAndBookAvailability':
        types = ['Flight', 'Hotel', 'Activity']
        return f"'{random.choice(types)}', {random.randint(1, 5000)}, '2026-09-{random.randint(1,28):02d}'"
    return ''

iteration = 0
while time.time() < end_time:
    try:
        sp_name = random.choice(stored_procedures)
        params = get_params(sp_name)
        sql = f"EXEC {sp_name} {params}"
        cursor.execute(sql)
        while cursor.nextset():
            pass
        iteration += 1
        if iteration % 10 == 0:
            print(f"Completed {iteration} calls...", flush=True)
        time.sleep(random.uniform(1, 3))
    except Exception as e:
        print(f"Error: {e}", flush=True)
        time.sleep(5)

cursor.close()
conn.close()
PYEOF

chmod 666 /tmp/travelapp_workload.py
export DB_HOST DB_USER DB_PASS DB_PORT END_TIME

# Start 8 concurrent workload processes
for i in {1..8}; do
  python3 /tmp/travelapp_workload.py &
done

echo "TravelHub workload started with 8 concurrent processes"
