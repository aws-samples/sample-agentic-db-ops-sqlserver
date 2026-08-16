from flask import Flask, jsonify, request, render_template_string
import subprocess
import os
import json
import time

app = Flask(__name__, static_folder='/workshop/labs/travelapp/static', static_url_path='/app/static')

DB_NAME = 'TravelHub'
WORKLOAD_SCRIPT = "/tmp/travelapp_workload.py"
STATE_FILE = "/tmp/travelapp_state.json"


def get_db_creds():
    import boto3
    region = os.environ.get('AWS_REGION', 'us-west-2')
    secret_id = os.environ.get('DB_SECRET_ID', 'dbops-infra-sqlserver-secret')
    client = boto3.client('secretsmanager', region_name=region)
    secret = client.get_secret_value(SecretId=secret_id)
    return json.loads(secret['SecretString'])


def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}


def save_state(config):
    with open(STATE_FILE, 'w') as f:
        json.dump(config, f)


def get_cpu_metric():
    try:
        import boto3
        from datetime import datetime, timedelta, timezone
        region = os.environ.get('AWS_REGION', 'us-west-2')
        db_id = os.environ.get('DB_INSTANCE_ID', 'dbops-infra-sqlserver')
        cw = boto3.client('cloudwatch', region_name=region)
        response = cw.get_metric_statistics(
            Namespace='AWS/RDS', MetricName='CPUUtilization',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=datetime.now(timezone.utc) - timedelta(minutes=10),
            EndTime=datetime.now(timezone.utc), Period=60, Statistics=['Average']
        )
        dps = sorted(response.get('Datapoints', []), key=lambda x: x['Timestamp'])
        return [{'time': dp['Timestamp'].strftime('%H:%M'), 'cpu': round(dp['Average'], 1)} for dp in dps]
    except:
        return []


def get_blocking_count():
    try:
        import pymssql
        creds = get_db_creds()
        conn = pymssql.connect(server=creds['host'], user=creds['username'],
                              password=creds['password'], port=int(creds['port']), database=DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id > 0")
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count
    except:
        return 0


SCENARIOS = [
    {'id': 'preferences', 'name': 'Preference Search', 'sp': 'sp_MatchDestinationsByPreferences', 'icon': '\U0001f50d', 'problem': 'CPU (join explosion)', 'default_workers': 10},
    {'id': 'text_search', 'name': 'Text Search', 'sp': 'sp_SearchDestinationsByDescription', 'icon': '\U0001f4dd', 'problem': 'I/O (full scans)', 'default_workers': 5},
    {'id': 'filter', 'name': 'Advanced Filter', 'sp': 'sp_FilterDestinationsAdvanced', 'icon': '\U0001f39b\ufe0f', 'problem': 'TempDB (contention)', 'default_workers': 20},
    {'id': 'flights', 'name': 'Flight Search', 'sp': 'sp_SearchFlightsByRoute', 'icon': '\u2708\ufe0f', 'problem': 'Plan sniffing', 'default_workers': 40},
    {'id': 'booking', 'name': 'Book Availability', 'sp': 'sp_CheckAndBookAvailability', 'icon': '\U0001f3ab', 'problem': 'Lock contention', 'default_workers': 10},
]

# ===== CSS VARIABLES =====
CSS_VARS = """
--primary: #2563eb;
--primary-hover: #1d4ed8;
--success: #10b981;
--danger: #ef4444;
--warning: #f59e0b;
--bg: #f8fafc;
--surface: #ffffff;
--border: #e2e8f0;
--text: #0f172a;
--text-muted: #64748b;
--text-light: #94a3b8;
--radius: 8px;
--shadow: 0 1px 3px rgba(0,0,0,0.05);
--shadow-md: 0 4px 6px rgba(0,0,0,0.07);
"""

# ===== LOAD RUNNER HTML =====
LOADRUNNER_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>TravelHub - Load Runner</title>
<style>
:root {""" + CSS_VARS + """}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
.container { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 20px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }
.badge { font-size: 11px; background: var(--warning); color: white; padding: 3px 8px; border-radius: 10px; font-weight: 600; }
.tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid var(--border); }
.tab { padding: 10px 20px; font-size: 13px; font-weight: 600; border-bottom: 2px solid transparent; margin-bottom: -2px; color: var(--text-muted); text-decoration: none; }
.tab:hover { color: var(--text); }
.tab.active { border-bottom-color: var(--primary); color: var(--primary); }
.card { background: var(--surface); border-radius: var(--radius); padding: 16px; margin-bottom: 12px; border: 1px solid var(--border); box-shadow: var(--shadow); }
.card-title { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
.status-bar { display: flex; align-items: center; justify-content: space-between; }
.status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; margin-right: 8px; }
.status-dot.on { background: var(--success); box-shadow: 0 0 8px var(--success); }
.status-dot.off { background: var(--text-light); }
.metric { font-size: 12px; color: var(--text-muted); }
.metric b { color: var(--text); }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-start { background: var(--success); color: white; }
.btn-stop { background: var(--danger); color: white; }
.btn-spike { background: var(--warning); color: var(--text); }
.btn-clear { background: var(--border); color: var(--text-muted); }
.controls { display: flex; gap: 8px; margin-bottom: 16px; }
.scenario { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: var(--bg); border-radius: 6px; border: 1px solid var(--border); margin-bottom: 6px; }
.scenario input[type=checkbox] { accent-color: var(--success); width: 15px; height: 15px; }
.scenario label { flex: 1; font-size: 12px; cursor: pointer; }
.scenario .hint { font-size: 10px; color: var(--text-light); }
.scenario input[type=number] { width: 50px; padding: 4px; border: 1px solid var(--border); border-radius: 4px; font-size: 12px; text-align: center; }
.scenario .badge-sm { font-size: 9px; padding: 2px 6px; border-radius: 8px; font-weight: 600; }
.badge-sm.on { background: #dcfce7; color: #166534; }
.badge-sm.off { background: #f1f5f9; color: var(--text-light); }
.cpu-chart { height: 80px; display: flex; align-items: flex-end; gap: 2px; }
.cpu-bar { flex: 1; background: var(--primary); border-radius: 2px 2px 0 0; min-width: 4px; transition: height 0.3s; }
.cpu-bar.high { background: var(--danger); }
.cpu-bar.med { background: var(--warning); }
.params { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.params label { font-size: 10px; color: var(--text-muted); display: block; margin-bottom: 3px; }
.params input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; font-size: 12px; }
.log { margin-top: 12px; padding: 10px; background: var(--bg); border-radius: 6px; border: 1px solid var(--border); font-family: monospace; font-size: 10px; color: var(--text-muted); height: 100px; overflow-y: auto; white-space: pre-wrap; }
</style>
</head>
<body>
<div class="container">
<h1><img src="/app/static/shark.png" style="height:28px;vertical-align:middle;margin-right:8px">ReefShark Adventures <span class="badge">Load Runner</span></h1>
<div class="tabs">
  <a href="/app/loadrunner/" class="tab active">\u26a1 Load Runner</a>
  <a href="/app/" class="tab">\U0001f50d Search</a>
</div>
<div class="card">
  <div class="status-bar">
    <div><span class="status-dot off" id="dot"></span><b id="statusText">Stopped</b></div>
    <div class="metric">Workers: <b id="wc">0</b> &nbsp; Blocking: <b id="bc">0</b></div>
  </div>
</div>
<div class="card"><div class="card-title">CPU (last 10 min)</div><div class="cpu-chart" id="cpu"></div></div>
<div class="controls">
  <button class="btn btn-start" onclick="start()">Start</button>
  <button class="btn btn-stop" onclick="stop()">Stop</button>
  <button class="btn btn-spike" onclick="spike()">\u26a1 Spike 60s</button>
  <button class="btn btn-clear" onclick="document.getElementById('log').innerHTML='';fetch('/app/api/clear-log',{method:'POST'})">Clear</button>
</div>
<div class="card"><div class="card-title">Scenarios</div><div id="scenarios"></div></div>
<div class="card"><div class="card-title">Parameters</div>
  <div class="params">
    <div><label>Sleep Min (s)</label><input type="number" id="smin" value="1" step="0.5"></div>
    <div><label>Sleep Max (s)</label><input type="number" id="smax" value="3" step="0.5"></div>
    <div><label>Duration (min)</label><input type="number" id="dur" value="4320"></div>
  </div>
</div>
<div class="log" id="log"></div>
</div>
<script>
const SC=SCENARIOS_JSON;
function init(){document.getElementById('scenarios').innerHTML=SC.map(s=>`<div class="scenario"><input type="checkbox" id="c_${s.id}" checked><span>${s.icon}</span><label for="c_${s.id}">${s.name} <span class="hint">(${s.problem})</span></label><input type="number" id="w_${s.id}" value="${s.default_workers}" min="0" max="100"><span class="badge-sm off" id="b_${s.id}">off</span></div>`).join('')}
function refresh(){fetch('/app/api/status?t='+Date.now()).then(r=>r.json()).then(d=>{document.getElementById('dot').className='status-dot '+(d.running?'on':'off');document.getElementById('statusText').textContent=d.running?'Running':'Stopped';document.getElementById('wc').textContent=d.workers;document.getElementById('bc').textContent=d.blocking||0;if(d.scenarios)d.scenarios.forEach(s=>{const b=document.getElementById('b_'+s.id);if(b){b.textContent=s.status;b.className='badge-sm '+(s.status==='running'?'on':'off')}});if(d.cpu_history&&d.cpu_history.length){document.getElementById('cpu').innerHTML=d.cpu_history.map(c=>{const h=Math.max(2,c.cpu*0.8);const cl=c.cpu>85?'high':c.cpu>60?'med':'';return`<div class="cpu-bar ${cl}" style="height:${h}%" title="${c.cpu}%"></div>`}).join('')}}).catch(()=>{})}
function getSel(){return SC.filter(s=>document.getElementById('c_'+s.id).checked).map(s=>({...s,workers:+document.getElementById('w_'+s.id).value}))}
function log(m,t){const l=document.getElementById('log');l.innerHTML+=new Date().toLocaleTimeString()+' '+m+'\\n';l.scrollTop=l.scrollHeight}
async function start(){const s=getSel();if(!s.length)return log('Select scenarios');const st=await fetch('/app/api/status?t='+Date.now()).then(r=>r.json());var totalW=s.reduce((a,x)=>a+x.workers,0);var msg='Start '+totalW+' workers across '+s.length+' SPs: '+s.map(x=>x.name).join(', ');if(st.running)msg+=' (will replace current '+st.workers+' workers)';if(!confirm(msg+'?'))return;log('Starting workers... please wait');document.getElementById('statusText').textContent='Starting...';const r=await fetch('/app/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenarios:s,sleep_min:+document.getElementById('smin').value,sleep_max:+document.getElementById('smax').value,duration:+document.getElementById('dur').value})});const d=await r.json();log(d.message);log('Refreshing in 3s...');setTimeout(refresh,3000)}
async function stop(){const st=await fetch('/app/api/status?t='+Date.now()).then(r=>r.json());if(!st.running){log('Nothing running');return}if(!confirm('Stop all '+st.workers+' workers?'))return;log('Stopping workers... please wait');document.getElementById('statusText').textContent='Stopping...';const r=await fetch('/app/api/stop',{method:'POST'});const d=await r.json();log(d.message);setTimeout(refresh,1500)}
async function spike(){const st=await fetch('/app/api/status?t='+Date.now()).then(r=>r.json());if(!st.running){log('Start workers first');return}var total=st.workers*2;if(!confirm('Current: '+st.workers+' workers running. Spike will add '+total+' extra workers (2x) for 60s. Proceed?'))return;log('Spiking... please wait');document.getElementById('statusText').textContent='Spiking...';const r=await fetch('/app/api/spike',{method:'POST'});const d=await r.json();log(d.message);setTimeout(refresh,2000)}
init();refresh();setInterval(refresh,5000);fetch('/app/api/log').then(r=>r.json()).then(d=>{const l=document.getElementById('log');l.innerHTML=d.entries.map(e=>e.msg).join('\\n');l.scrollTop=l.scrollHeight}).catch(()=>{});
</script>
</body>
</html>"""

# ===== SEARCH HTML =====
SEARCH_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>TravelHub - Search</title>
<style>
:root {""" + CSS_VARS + """}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }
.container { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 20px; margin-bottom: 16px; }
.tabs { display: flex; margin-bottom: 20px; border-bottom: 2px solid var(--border); }
.tab { padding: 10px 20px; font-size: 13px; font-weight: 600; border-bottom: 2px solid transparent; margin-bottom: -2px; color: var(--text-muted); text-decoration: none; }
.tab:hover { color: var(--text); }
.tab.active { border-bottom-color: var(--primary); color: var(--primary); }
.search-row { display: flex; gap: 8px; margin-bottom: 16px; }
.search-row input { flex: 1; padding: 12px 16px; border: 2px solid var(--border); border-radius: var(--radius); font-size: 14px; outline: none; }
.search-row button { padding: 12px 24px; background: var(--primary); color: white; border: none; border-radius: var(--radius); font-size: 13px; font-weight: 600; cursor: pointer; }
.chips { margin-bottom: 16px; }
.chips span { display: inline-block; padding: 5px 10px; background: #f1f5f9; border: 1px solid var(--border); border-radius: 12px; font-size: 11px; cursor: pointer; margin: 2px 4px 2px 0; }
.chips span:hover { background: var(--border); }
.loading { text-align: center; padding: 30px; display: none; }
.loading.on { display: block; }
.spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.result { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 18px; margin-bottom: 10px; box-shadow: var(--shadow); }
.result h3 { font-size: 15px; margin-bottom: 4px; }
.result p { font-size: 12px; color: var(--text-muted); line-height: 1.5; margin-bottom: 8px; }
.result .tags { display: flex; gap: 6px; font-size: 10px; }
.result .tags span { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }
.result .score { float: right; font-size: 12px; font-weight: 600; color: var(--success); }
.rag { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: var(--radius); padding: 12px 16px; margin-top: 16px; }
.rag h4 { font-size: 12px; color: #1d4ed8; margin-bottom: 8px; }
.rag .chunk { font-size: 11px; color: #475569; margin-bottom: 6px; padding-left: 10px; border-left: 2px solid #93c5fd; }
.rag .src { font-size: 10px; color: var(--primary); font-weight: 600; }
.meta { font-size: 11px; color: var(--text-light); margin-top: 12px; padding: 8px 12px; background: #fffbeb; border: 1px solid #fde68a; border-radius: var(--radius); }
.empty { text-align: center; padding: 40px; color: var(--text-light); }
</style>
</head>
<body>
<div class="container">
<h1><img src="/app/static/shark.png" style="height:28px;vertical-align:middle;margin-right:8px">ReefShark Adventures</h1>
<img src="/app/static/hero.jpg" style="width:100%;height:250px;object-fit:cover;object-position:center;border-radius:var(--radius);margin-bottom:16px;width:100%;border-radius:var(--radius);margin-bottom:16px" alt="TravelHub">
<div class="tabs">
  <a href="/app/" class="tab">\u26a1 Load Runner</a>
  <a href="/app/search/" class="tab active">\U0001f50d Search</a>
</div>
<div class="chips">
  <span onclick="q(this)">eco-friendly beach snorkeling</span>
  <span onclick="q(this)">luxury tropical island romantic</span>
  <span onclick="q(this)">family adventure hiking wildlife</span>
  <span onclick="q(this)">budget sustainable eco tourism</span>
  <span onclick="q(this)">cultural museums architecture</span>
</div>
<div class="search-row">
  <input type="text" id="inp" placeholder="Describe your ideal trip..."
    onfocus="this.style.borderColor='var(--primary)'" onblur="this.style.borderColor='var(--border)'">
  <button onclick="search()"
    onmouseenter="this.style.background='var(--primary-hover)'" onmouseleave="this.style.background='var(--primary)'">Search</button>
</div>
<div class="loading" id="load"><div class="spinner"></div><p style="margin-top:8px;color:var(--text-muted)">Searching via usp_TravelSearch...</p></div>
<div id="results"></div>
</div>
<script>
function q(el){document.getElementById('inp').value=el.textContent}
document.getElementById('inp').addEventListener('keydown',e=>{if(e.key==='Enter')search()});
async function search(){
  const v=document.getElementById('inp').value.trim();if(!v)return;
  document.getElementById('load').className='loading on';
  document.getElementById('results').innerHTML='';
  try{
    const r=await fetch('/app/api/search?t='+Date.now(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:v})});
    const d=await r.json();
    document.getElementById('load').className='loading';
    if(d.error){document.getElementById('results').innerHTML=`<div class="empty" style="color:var(--danger)">${d.error}</div>`;return}
    let html='';
    const strats=d.strategies;
    const keys=Object.keys(strats);
    // Strategy tabs
    html+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px">';
    keys.forEach((k,i)=>{const s=strats[k];const win=k===d.winner?' style="border-color:var(--success);background:#f0fdf4"':'';html+=`<div class="card" id="tab_${k}" onclick="showStrat('${k}')" style="cursor:pointer;padding:10px 14px;border-left:4px solid ${['var(--warning)','#8b5cf6','var(--primary)','var(--success)'][i]};${k===d.winner?'border-color:var(--success);background:#f0fdf4':''}"><b style="font-size:12px">${s.name}</b><div style="font-size:10px;color:var(--text-light);margin-top:2px">${s.latency}ms | ${s.count} results</div></div>`});
    html+='</div>';
    // Strategy panels
    keys.forEach((k,i)=>{const s=strats[k];const vis=i===keys.length-1?'':'display:none;';
      html+=`<div class="strat-panel" id="panel_${k}" style="${vis}"><div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;padding:6px 10px;background:var(--bg);border-radius:4px">${s.description}</div>`;
      if(s.results&&s.results.length){s.results.forEach(r=>{html+=`<div class="result"><span class="score">${r.score}</span><h3>${r.icon} ${r.name}</h3><p>${r.description}</p><div class="tags"><span>${r.country}</span><span>${r.climate}</span><span>${r.season}</span></div></div>`})}
      else{html+='<div class="empty">No results for this strategy</div>'}
      if(s.rag_context&&s.rag_context.length){html+='<div class="rag"><h4>\U0001f4da RAG Context</h4>';s.rag_context.forEach(c=>{html+=`<div class="chunk"><span class="src">${c.source}:</span> ${c.snippet}</div>`});html+='</div>'}
      html+='</div>'});
    if(d.vector_note){html+=`<div class="meta">\U0001f4a1 ${d.vector_note}</div>`}
    document.getElementById('results').innerHTML=html;
  }catch(e){document.getElementById('load').className='loading';document.getElementById('results').innerHTML=`<div class="empty" style="color:var(--danger)">Error: ${e.message}</div>`}
}
function showStrat(k){document.querySelectorAll('.strat-panel').forEach(p=>p.style.display='none');document.getElementById('panel_'+k).style.display='block'}
</script>
</body>
</html>"""

# ===== WORKLOAD TEMPLATE =====
WORKLOAD_TEMPLATE = """
import pymssql, random, time, os
host=os.environ['DB_HOST'];user=os.environ['DB_USER'];password=os.environ['DB_PASS']
port=int(os.environ['DB_PORT']);end_time=int(os.environ['END_TIME'])
sleep_min=float(os.environ.get('SLEEP_MIN','1'));sleep_max=float(os.environ.get('SLEEP_MAX','3'))
sp_name=os.environ.get('SP_NAME','sp_FilterDestinationsAdvanced')
conn=pymssql.connect(server=host,user=user,password=password,port=port,database='TravelHub')
cursor=conn.cursor()
def params(sp):
    if sp=='sp_MatchDestinationsByPreferences':return str(random.randint(1,1000))
    elif sp=='sp_SearchDestinationsByDescription':return"'"+random.choice(['beach resort','eco-friendly diving','luxury spa','adventure hiking','family snorkeling'])+"'"
    elif sp=='sp_FilterDestinationsAdvanced':return f"{random.randint(50,200)},{random.randint(300,800)},{random.uniform(3.0,4.5):.1f}"
    elif sp=='sp_SearchFlightsByRoute':return f"'{random.choice(['JFK','LAX','ORD','ATL','DFW'])}','{random.choice(['CDG','NRT','LHR','SYD','DXB'])}'"
    elif sp=='sp_CheckAndBookAvailability':return f"'{random.choice(['Flight','Hotel'])}',{random.randint(1,180)},'2026-09-{random.randint(1,28):02d}'"
    return''
while time.time()<end_time:
    try:cursor.execute(f"EXEC {sp_name} {params(sp_name)}");cursor.nextset();time.sleep(random.uniform(sleep_min,sleep_max))
    except:time.sleep(3)
cursor.close();conn.close()
"""


# ===== MIDDLEWARE =====
@app.after_request
def no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


# ===== ROUTES: LOAD RUNNER =====
@app.route('/app/loadrunner/')
def loadrunner():
    return render_template_string(LOADRUNNER_HTML.replace('SCENARIOS_JSON', json.dumps(SCENARIOS)))

@app.route('/app/api/status')
def status():
    result = subprocess.run(['pgrep', '-f', 'travelapp_workload'], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split('\n') if p]
    state = load_state()
    active = state.get('scenarios', [])
    return jsonify({
        'running': len(pids) > 0, 'workers': len(pids),
        'scenarios': [{'id': s['id'], 'status': 'running' if any(a['id']==s['id'] for a in active) and len(pids)>0 else 'stopped'} for s in SCENARIOS],
        'cpu_history': get_cpu_metric(), 'blocking': get_blocking_count()
    })

@app.route('/app/api/start', methods=['POST'])
def start():
    subprocess.run(['pkill', '-f', 'travelapp_workload'], capture_output=True)
    time.sleep(1)
    p = request.json or {}
    scenarios = p.get('scenarios', [])
    try: os.remove(WORKLOAD_SCRIPT)
    except: subprocess.run(['sudo','rm','-f',WORKLOAD_SCRIPT], capture_output=True)
    with open(WORKLOAD_SCRIPT, 'w') as f: f.write(WORKLOAD_TEMPLATE)
    os.chmod(WORKLOAD_SCRIPT, 0o666)
    try: creds = get_db_creds()
    except Exception as e: return jsonify({'message': f'Error: {e}'}), 500
    end_time = int(time.time()) + p.get('duration', 4320) * 60
    total = 0
    for sc in scenarios:
        w = sc.get('workers', sc.get('default_workers', 5))
        env = os.environ.copy()
        env.update({'DB_HOST':creds['host'],'DB_USER':creds['username'],'DB_PASS':creds['password'],'DB_PORT':str(creds['port']),'END_TIME':str(end_time),'SLEEP_MIN':str(p.get('sleep_min',1)),'SLEEP_MAX':str(p.get('sleep_max',3)),'SP_NAME':sc['sp']})
        for _ in range(w): subprocess.Popen(['python3',WORKLOAD_SCRIPT],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        total += w
    save_state({'scenarios': scenarios, 'total': total})
    return jsonify({'message': f'Started {total} workers | {", ".join(s["name"] for s in scenarios)}'})

@app.route('/app/api/stop', methods=['POST'])
def stop():
    subprocess.run(['pkill', '-f', 'travelapp_workload'], capture_output=True)
    save_state({})
    return jsonify({'message': 'Stopped'})

@app.route('/app/api/spike', methods=['POST'])
def spike():
    state = load_state()
    scenarios = state.get('scenarios', [])
    if not scenarios: return jsonify({'message': 'Start first'}), 400
    try: creds = get_db_creds()
    except Exception as e: return jsonify({'message': f'Error: {e}'}), 500
    end_time = int(time.time()) + 60
    total = 0
    for sc in scenarios:
        w = sc.get('workers', 5) * 2
        env = os.environ.copy()
        env.update({'DB_HOST':creds['host'],'DB_USER':creds['username'],'DB_PASS':creds['password'],'DB_PORT':str(creds['port']),'END_TIME':str(end_time),'SLEEP_MIN':'0.1','SLEEP_MAX':'0.5','SP_NAME':sc['sp']})
        for _ in range(w): subprocess.Popen(['python3',WORKLOAD_SCRIPT],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        total += w
    return jsonify({'message': f'Spike: {total} workers for 60s'})


# ===== ROUTES: SEARCH =====
@app.route('/app/')
def index():
    with open('/workshop/labs/travelapp/search_ui.html', 'r') as f: return f.read()

@app.route('/app/api/search', methods=['POST'])
def search_api():
    import pymssql
    query = (request.json or {}).get('query', '')
    icons = {'Asia':'\U0001f3ef','Europe':'\U0001f3f0','Oceania':'\U0001f3dd\ufe0f','Africa':'\U0001f30d','North America':'\U0001f30e','South America':'\U0001f30e'}
    def fmt(rows):
        return [{'name':r['Title'],'country':r['Country'],'climate':r['Climate'],'season':r['Season'],'description':r['Snippet'] or '','score':round(r['RelevanceScore']/200.0,2) if r.get('RelevanceScore') else 0,'icon':icons.get(r.get('Continent',''),'\U0001f4cd')} for r in rows]
    try:
        creds = get_db_creds()
        conn = pymssql.connect(server=creds['host'], user=creds['username'], password=creds['password'], port=int(creds['port']), database='TravelAI')
        cur = conn.cursor(as_dict=True)

        # Strategy 1: SQL Only
        t0 = time.time()
        cur.execute("EXEC usp_SearchSQL %s", (query,))
        sql_rows = cur.fetchall()
        sql_ms = int((time.time()-t0)*1000)

        # Strategy 2: LIKE
        t0 = time.time()
        cur.execute("EXEC usp_SearchLIKE %s", (query,))
        like_rows = cur.fetchall()
        like_ms = int((time.time()-t0)*1000)

        # Strategy 3: FREETEXT
        t0 = time.time()
        cur.execute("EXEC usp_SearchFreetext %s", (query,))
        fts_rows = cur.fetchall()
        fts_ms = int((time.time()-t0)*1000)

        # Strategy 4: Hybrid (FREETEXT + RAG)
        t0 = time.time()
        cur.execute("EXEC usp_TravelSearch %s", (query,))
        hybrid_rows = cur.fetchall()
        chunks = []
        if cur.nextset():
            chunks = cur.fetchall()
        hybrid_ms = int((time.time()-t0)*1000)

        # Strategy 5: Vector (VECTOR_DISTANCE via Bedrock embedding)
        vec_rows = []
        vec_ms = 0
        try:
            import boto3 as _b3
            _bedrock = _b3.client('bedrock-runtime', region_name='us-west-2')
            _emb_resp = _bedrock.invoke_model(modelId='amazon.titan-embed-text-v2:0', contentType='application/json', accept='application/json', body=json.dumps({'inputText': query[:8000], 'dimensions': 1024}))
            _emb = json.loads(_emb_resp['body'].read())['embedding']
            _vec_json = json.dumps(_emb)
            t0 = time.time()
            cur.execute("DECLARE @qv VECTOR(1024) = CAST(%s AS VECTOR(1024)); EXEC usp_SearchVector @qv, 5", (_vec_json,))
            vec_rows = cur.fetchall()
            vec_ms = int((time.time()-t0)*1000)
        except:
            pass

        conn.close()

        rag = [{'source':c['Title'],'snippet':c['Snippet'] or ''} for c in chunks]

        return jsonify({
            'query': query, 'winner': 'hybrid',
            'vector_note': 'All strategies active. Semantic uses Titan V2 1024-dim embeddings with VECTOR_DISTANCE cosine.' if vec_rows else 'Vector search (VECTOR_DISTANCE) activates once Bedrock embeddings are populated.',
            'strategies': {
                'semantic': {'name':'Semantic (VECTOR_DISTANCE)','description':'Cosine similarity via Titan V2 embeddings.','latency':vec_ms,'results':fmt(vec_rows),'count':len(vec_rows)},
                'sql_only': {'name':'SQL Only (WHERE)','description':'Pure SQL filtering by climate keyword. Fast but low relevance.','latency':sql_ms,'results':fmt(sql_rows),'count':len(sql_rows)},
                'like': {'name':'LIKE Pattern','description':'LIKE matching on descriptions. Exact substring match only.','latency':like_ms,'results':fmt(like_rows),'count':len(like_rows)},
                'freetext': {'name':'Full-Text (FREETEXT)','description':'SQL Server Full-Text Search with stemming and word forms.','latency':fts_ms,'results':fmt(fts_rows),'count':len(fts_rows)},
                'hybrid': {'name':'Hybrid (FTS + RAG)','description':'FREETEXT + document chunk retrieval for context enrichment.','latency':hybrid_ms,'results':fmt(hybrid_rows),'count':len(hybrid_rows),'rag_context':rag}
            }
        })
    except Exception as e:
        return jsonify({'error': str(e), 'strategies': {}, 'winner': None}), 500


LOG_FILE = "/tmp/travelapp_runner.log"

@app.route('/app/api/log', methods=['GET'])
def get_log():
    try:
        with open(LOG_FILE, 'r') as f:
            entries = [json.loads(line) for line in f.readlines()[-50:]]
    except:
        entries = []
    return jsonify({'entries': entries})

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081)
