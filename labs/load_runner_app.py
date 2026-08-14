from flask import Flask, jsonify, request, render_template_string
import subprocess
import os
import json
import time
import re

app = Flask(__name__)

WORKLOAD_SCRIPT = "/tmp/sp_workload.py"
DB_NAME = os.environ.get('DB_NAME', 'DBOpsLab')


def get_db_creds():
    import boto3
    region = os.environ.get('AWS_REGION', 'us-west-2')
    secret_id = os.environ.get('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
    client = boto3.client('secretsmanager', region_name=region)
    secret = client.get_secret_value(SecretId=secret_id)
    return json.loads(secret['SecretString'])


def get_stored_procedures():
    try:
        creds = get_db_creds()
        import pymssql
        conn = pymssql.connect(server=creds['host'], user=creds['username'], password=creds['password'], port=int(creds['port']), database=DB_NAME)
        cur = conn.cursor()
        cur.execute("""
            SELECT name FROM sys.procedures
            WHERE is_ms_shipped = 0 AND name LIKE 'sp_%'
            ORDER BY name
        """)
        sps = [{'name': row[0], 'default': row[0] == 'sp_MonthlyOrderReport'} for row in cur.fetchall()]
        cur.close()
        conn.close()
        return sps
    except Exception as e:
        return [{'name': 'sp_MonthlyOrderReport', 'default': True}]


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Autonomous DBOps - Load Runner</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1e293b; padding: 32px; }
        .container { max-width: 720px; margin: 0 auto; }
        h1 { font-size: 22px; margin-bottom: 20px; color: #0f172a; letter-spacing: -0.5px; }

        .status-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: #ffffff; border-radius: 10px; margin-bottom: 20px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .status-left { display: flex; align-items: center; gap: 12px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .status-dot.running { background: #10b981; box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite; }
        .status-dot.stopped { background: #94a3b8; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .status-label { font-size: 14px; font-weight: 600; color: #0f172a; }
        .status-meta { font-size: 12px; color: #64748b; margin-top: 2px; }
        .status-right { text-align: right; }
        .status-workers { font-size: 28px; font-weight: 700; color: #0f172a; }
        .status-workers-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }

        .controls { display: flex; gap: 8px; margin-bottom: 20px; }
        button { padding: 9px 18px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
        button:hover { transform: translateY(-1px); }
        button:active { transform: translateY(0); }
        .btn-start { background: #10b981; color: white; }
        .btn-stop { background: #ef4444; color: white; }
        .btn-clear { background: #e2e8f0; color: #475569; }

        .section { background: #ffffff; border-radius: 10px; padding: 16px 20px; margin-bottom: 16px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .section-title { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

        .sp-list { display: flex; flex-direction: column; gap: 6px; }
        .sp-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: #f8fafc; border-radius: 6px; border: 1px solid #e2e8f0; transition: border-color 0.15s; }
        .sp-item:hover { border-color: #cbd5e1; }
        .sp-item input[type="checkbox"] { accent-color: #10b981; width: 16px; height: 16px; }
        .sp-item label { flex: 1; font-size: 13px; cursor: pointer; color: #1e293b; }
        .sp-item .sp-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
        .sp-badge.running { background: #d1fae5; color: #065f46; }
        .sp-badge.stopped { background: #f1f5f9; color: #94a3b8; }

        .params { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
        .param-group label { font-size: 11px; color: #64748b; display: block; margin-bottom: 4px; }
        .param-group input { width: 100%; padding: 8px 10px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 5px; color: #1e293b; font-size: 14px; }
        .param-group input:focus { outline: none; border-color: #3b82f6; }

        .log { margin-top: 16px; padding: 12px 14px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #475569; height: 120px; overflow-y: auto; white-space: pre-wrap; }
        .log .info { color: #64748b; }
        .log .success { color: #059669; }
        .log .error { color: #dc2626; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Autonomous DBOps: Agentic AI for maintaining RDS SQL Server</h1>

        <div class="status-card">
            <div class="status-left">
                <div class="status-dot" id="statusDot"></div>
                <div>
                    <div class="status-label" id="statusText">Checking...</div>
                    <div class="status-meta" id="statusMeta"></div>
                </div>
            </div>
            <div class="status-right">
                <div class="status-workers" id="workerCount">-</div>
                <div class="status-workers-label">workers</div>
            </div>
        </div>

        <div class="controls">
            <button class="btn-start" onclick="startLoad()">Start</button>
            <button class="btn-stop" onclick="stopLoad()">Stop</button>
            <button class="btn-clear" onclick="clearLog()">Clear Log</button>
        </div>

        <div class="section">
            <div class="section-title">Stored Procedures</div>
            <div class="sp-list" id="spList"></div>
        </div>

        <div class="section">
            <div class="section-title">Parameters</div>
            <div class="params">
                <div class="param-group">
                    <label>Workers</label>
                    <input type="number" id="workers" value="8" min="1" max="20">
                </div>
                <div class="param-group">
                    <label>Sleep Min (s)</label>
                    <input type="number" id="sleepMin" value="2" min="0" max="30" step="0.5">
                </div>
                <div class="param-group">
                    <label>Sleep Max (s)</label>
                    <input type="number" id="sleepMax" value="5" min="1" max="60" step="0.5">
                </div>
            </div>
        </div>

        <div class="log" id="log"></div>
    </div>

    <script>
        const SPS = STORED_PROCEDURES_JSON;

        let spsRendered = false;
        function renderSPs(statuses) {
            const list = document.getElementById('spList');
            if (!spsRendered) {
                list.innerHTML = SPS.map(sp => `
                <div class="sp-item">
                    <input type="checkbox" id="sp_${sp.name}" ${sp.default ? 'checked' : ''}>
                    <label for="sp_${sp.name}">${sp.name}</label>
                    <span class="sp-badge stopped" id="badge_${sp.name}">stopped</span>
                </div>`).join('');
                spsRendered = true;
            }
            if (statuses) {
                statuses.forEach(st => {
                    const badge = document.getElementById('badge_' + st.name);
                    if (badge) {
                        badge.textContent = st.status;
                        badge.className = 'sp-badge ' + st.status;
                    }
                });
            }
        }

        function getSelectedSPs() {
            return SPS.filter(sp => document.getElementById('sp_' + sp.name).checked).map(sp => sp.name);
        }

        async function refreshStatus() {
            try {
                const res = await fetch('/app/api/status?t=' + Date.now());
                const data = await res.json();
                applyStatus(data);
            } catch(e) {}
        }

        async function startLoad() {
            const sps = getSelectedSPs();
            if (sps.length === 0) { log('Select at least one stored procedure.', 'error'); return; }
            const params = {
                procedures: sps,
                workers: parseInt(document.getElementById('workers').value),
                sleep_min: parseFloat(document.getElementById('sleepMin').value),
                sleep_max: parseFloat(document.getElementById('sleepMax').value)
            };
            log('Starting | workers: ' + params.workers + ' | SPs: ' + sps.join(', ') + ' | interval: ' + params.sleep_min + '-' + params.sleep_max + 's', 'info');
            const res = await fetch('/app/api/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(params) });
            const data = await res.json();
            if (res.ok) { log(data.message, 'success'); } else { log(data.message, 'error'); }
            setTimeout(refreshStatus, 1500);
        }

        async function stopLoad() {
            log('Stopping all workers...', 'info');
            const res = await fetch('/app/api/stop', { method: 'POST' });
            const data = await res.json();
            log(data.message, 'success');
            setTimeout(refreshStatus, 1500);
        }

        function clearLog() {
            fetch('/app/api/clear-log?t=' + Date.now(), { method: 'POST' });
            document.getElementById('log').innerHTML = '';
        }

        function log(msg, type) {
            const el = document.getElementById('log');
            const ts = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
            const line = '<span class="' + (type||'info') + '">' + ts + '  ' + msg + '</span>\\n';
            el.innerHTML += line;
            el.scrollTop = el.scrollHeight;
            fetch('/app/api/log', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({msg: ts + '  ' + msg, type: type||'info'}) });
        }

        // Load log from server on page load
        (async function() {
            const res = await fetch('/app/api/log?t=' + Date.now());
            const data = await res.json();
            const el = document.getElementById('log');
            el.innerHTML = data.entries.map(e => '<span class="' + e.type + '">' + e.msg + '</span>').join('\\n');
            el.scrollTop = el.scrollHeight;
        })();

        const initialStatus = INITIAL_STATUS_JSON;
        function applyStatus(data) {
            const dot = document.getElementById('statusDot');
            const text = document.getElementById('statusText');
            const meta = document.getElementById('statusMeta');
            const count = document.getElementById('workerCount');
            if (data.running) {
                dot.className = 'status-dot running';
                text.textContent = 'Running';
                const running = data.procedures.filter(p => p.status === 'running').map(p => p.name);
                meta.textContent = running.join(', ');
                count.textContent = data.workers;
            } else {
                dot.className = 'status-dot stopped';
                text.textContent = 'Stopped';
                meta.textContent = '';
                count.textContent = '0';
            }
            renderSPs(data.procedures);
        }
        applyStatus(initialStatus);
        setInterval(refreshStatus, 3000);
    </script>
</body>
</html>
"""

WORKLOAD_TEMPLATE = """
import pymssql
import random
import time
import os

host = os.environ['DB_HOST']
user = os.environ['DB_USER']
password = os.environ['DB_PASS']
port = int(os.environ['DB_PORT'])
end_time = int(os.environ['END_TIME'])
sleep_min = float(os.environ.get('SLEEP_MIN', '2'))
sleep_max = float(os.environ.get('SLEEP_MAX', '5'))
procedures = os.environ.get('PROCEDURES', 'sp_MonthlyOrderReport').split(',')

db_name = os.environ.get('DB_NAME', 'DBOpsLab')
conn = pymssql.connect(server=host, user=user, password=password, port=port, database=db_name)
cursor = conn.cursor()

iteration = 0
while time.time() < end_time:
    try:
        sp_name = random.choice(procedures)
        cursor.execute(f"EXEC {sp_name}")
        while cursor.nextset():
            pass
        iteration += 1
        if iteration % 10 == 0:
            print(f"Completed {iteration} calls...", flush=True)
        time.sleep(random.uniform(sleep_min, sleep_max))
    except Exception as e:
        print(f"Error: {e}", flush=True)
        time.sleep(10)

cursor.close()
conn.close()
"""

# Track what's running — persist to disk
STATE_FILE = "/tmp/load_runner_state.json"

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(config):
    with open(STATE_FILE, 'w') as f:
        json.dump(config, f)

active_config = load_state()

# On startup, detect if workers are already running (e.g. started by bootstrap)
if not active_config:
    import subprocess as _sp
    _result = _sp.run(['pgrep', '-f', 'sp_workload'], capture_output=True, text=True)
    _pids = [p for p in _result.stdout.strip().split('\n') if p]
    if _pids:
        active_config = {'procedures': ['sp_MonthlyOrderReport'], 'workers': len(_pids)}
        save_state(active_config)


@app.route('/app/')
def index():
    result = subprocess.run(['pgrep', '-f', 'sp_workload'], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split('\n') if p]
    running = len(pids) > 0
    stored_procedures = get_stored_procedures()
    state = load_state()
    procedures = state.get('procedures', [])
    if running and not procedures:
        procedures = ['sp_MonthlyOrderReport']
        save_state({'procedures': procedures, 'workers': len(pids)})
    initial_status = json.dumps({'running': running, 'workers': len(pids), 'procedures': [
        {'name': sp['name'], 'status': 'running' if sp['name'] in procedures and running else 'stopped'}
        for sp in stored_procedures
    ]})
    html = HTML_TEMPLATE.replace('STORED_PROCEDURES_JSON', json.dumps(stored_procedures))
    html = html.replace('INITIAL_STATUS_JSON', initial_status)
    resp = app.make_response(render_template_string(html))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


LOG_FILE = "/tmp/load_runner_ui.log"


@app.route('/app/api/log', methods=['GET'])
def get_log():
    try:
        with open(LOG_FILE, 'r') as f:
            entries = [json.loads(line) for line in f.readlines()[-100:]]
    except:
        entries = []
    resp = jsonify({'entries': entries})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/app/api/log', methods=['POST'])
def append_log():
    entry = request.json or {}
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    return jsonify({'ok': True})


@app.route('/app/api/clear-log', methods=['POST'])
def clear_log():
    open(LOG_FILE, 'w').close()
    return jsonify({'ok': True})


@app.route('/app/api/status')
def status():
    result = subprocess.run(['pgrep', '-f', 'sp_workload'], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split('\n') if p]
    running = len(pids) > 0
    workers = len(pids)
    stored_procedures = get_stored_procedures()

    # Detect actual running SPs from /tmp/sp_workload.py (truth source)
    procedures = []
    try:
        with open('/tmp/sp_workload.py', 'r') as f:
            script_content = f.read()
        match = re.search(r"stored_procedures\s*=\s*\[([^\]]+)\]", script_content)
        if match:
            items = match.group(1)
            procedures = [s.strip().strip("'").strip('"') for s in items.split(',')
                         if s.strip() and not s.strip().startswith('#')]
    except:
        pass

    # Fall back to state file if script not readable
    if not procedures:
        state = load_state()
        procedures = state.get('procedures', ['sp_MonthlyOrderReport'])

    sp_status = []
    for sp in stored_procedures:
        if sp['name'] in procedures and running:
            sp_status.append({'name': sp['name'], 'status': 'running'})
        else:
            sp_status.append({'name': sp['name'], 'status': 'stopped'})
    return jsonify({'running': running, 'workers': workers, 'procedures': sp_status})


@app.route('/app/api/start', methods=['POST'])
def start():
    global active_config
    subprocess.run(['pkill', '-f', 'sp_workload'], capture_output=True)
    time.sleep(1)

    params = request.json or {}
    procedures = params.get('procedures', ['sp_MonthlyOrderReport'])
    workers = params.get('workers', 8)
    sleep_min = params.get('sleep_min', 2)
    sleep_max = params.get('sleep_max', 5)
    duration = params.get('duration', 4320)

    # Remove existing workload script if owned by root (boot creates it as root)
    try:
        os.remove(WORKLOAD_SCRIPT)
    except (PermissionError, FileNotFoundError):
        try:
            subprocess.run(['sudo', 'rm', '-f', WORKLOAD_SCRIPT], capture_output=True)
        except Exception:
            pass

    with open(WORKLOAD_SCRIPT, 'w') as f:
        f.write(WORKLOAD_TEMPLATE)

    try:
        creds = get_db_creds()
    except Exception as e:
        return jsonify({'message': f'Error getting DB credentials: {e}'}), 500

    end_time = int(time.time()) + duration * 60
    env = os.environ.copy()
    env.update({
        'DB_HOST': creds['host'],
        'DB_USER': creds['username'],
        'DB_PASS': creds['password'],
        'DB_PORT': str(creds['port']),
        'DB_NAME': DB_NAME,
        'END_TIME': str(end_time),
        'SLEEP_MIN': str(sleep_min),
        'SLEEP_MAX': str(sleep_max),
        'PROCEDURES': ','.join(procedures),
    })

    for i in range(workers):
        subprocess.Popen(['python3', WORKLOAD_SCRIPT], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    active_config = {'procedures': procedures, 'workers': workers, 'sleep_min': sleep_min, 'sleep_max': sleep_max}
    save_state(active_config)
    return jsonify({'message': f'Started | workers: {workers} | SPs: {", ".join(procedures)} | interval: {sleep_min}-{sleep_max}s | duration: {duration}min | db: {DB_NAME}'})


@app.route('/app/api/stop', methods=['POST'])
def stop():
    global active_config
    subprocess.run(['pkill', '-f', 'sp_workload'], capture_output=True)
    subprocess.run(['pkill', '-f', 'start_benchmark'], capture_output=True)
    active_config = {}
    save_state(active_config)
    return jsonify({'message': 'Stopped'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)
