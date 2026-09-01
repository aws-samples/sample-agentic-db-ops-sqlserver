"""Load-generation control for the SRE console.

Spawns/kills a pool of tagged worker processes (console_workload.py) that drive a
read-only proc mix against TravelHub. Tagged so Stop only affects console load,
not the standalone benchmark. Capped for safety on the small RDS instance.
"""
import os
import time
import subprocess

import db

WORKLOAD_PATH = "/tmp/console_workload.py"
LOG = "/tmp/console_load.log"
MAX_WORKERS = 64
TAG = "console_workload.py"

WORKLOAD_SRC = r'''
import pymssql, random, time, os
host=os.environ["DB_HOST"]; user=os.environ["DB_USER"]; password=os.environ["DB_PASS"]
port=int(os.environ["DB_PORT"]); end_time=int(os.environ["END_TIME"])
tmin=float(os.environ.get("THINK_MIN","0.05")); tmax=float(os.environ.get("THINK_MAX","0.2"))
conn=pymssql.connect(server=host,user=user,password=password,port=port,database="TravelHub")
cur=conn.cursor()
procs=["sp_SearchFlightsByRoute"]*6+["sp_SearchDestinationsByDescription"]
def params(sp):
    if sp=="sp_SearchFlightsByRoute":
        o=random.choice(["JFK","LAX","ORD","ATL","DFW","SFO","MIA"]) ; d=random.choice(["CDG","NRT","LHR","SYD","DXB","SIN","FCO"]) ; return "'%s','%s'"%(o,d)
    if sp=="sp_SearchDestinationsByDescription":
        return "'%s'"%random.choice(["beach resort","luxury spa","adventure hiking"])
    return ""
while time.time()<end_time:
    try:
        sp=random.choice(procs); cur.execute("EXEC %s %s"%(sp,params(sp)))
        while cur.nextset(): pass
        time.sleep(random.uniform(tmin,tmax))
    except Exception:
        time.sleep(2)
try:
    cur.close(); conn.close()
except Exception:
    pass
'''


def _ensure_script():
    with open(WORKLOAD_PATH, "w") as f:
        f.write(WORKLOAD_SRC)


def running_count():
    r = subprocess.run(["pgrep", "-fc", TAG], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def start(workers, think_min=0.05, think_max=0.2, duration_min=120):
    workers = max(1, min(int(workers), MAX_WORKERS))
    _ensure_script()
    c = db._creds()
    env = dict(os.environ)
    env.update({
        "DB_HOST": c["host"], "DB_USER": c["username"], "DB_PASS": c["password"],
        "DB_PORT": str(c["port"]), "END_TIME": str(int(time.time()) + duration_min * 60),
        "THINK_MIN": str(think_min), "THINK_MAX": str(think_max),
    })
    logf = open(LOG, "a")
    for _ in range(workers):
        subprocess.Popen(["python3.11", WORKLOAD_PATH], env=env,
                         stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(1)
    return {"started": workers, "running": running_count(), "capped_at": MAX_WORKERS}


def stop():
    subprocess.run(["pkill", "-f", TAG])
    time.sleep(1)
    return {"running": running_count()}
