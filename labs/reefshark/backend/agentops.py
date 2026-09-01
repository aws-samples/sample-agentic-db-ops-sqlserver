"""Real agent activity for the SRE console: alerts + remediation trace.

Alerts are derived from the DynamoDB approval-requests table plus a live CPU
health line. The remediation trace is built from the latest approval request,
the current top query (procedure stats), and CPU before/after (from the 10-min
CloudWatch series).
"""
import os
import functools
from datetime import datetime, timezone

import boto3
import db

APPROVAL_TABLE = os.getenv("APPROVAL_TABLE", "dbops-approval-requests")


@functools.lru_cache(maxsize=1)
def _ddb():
    return boto3.client("dynamodb", region_name=db.REGION)


def _s(item, k, default=None):
    v = item.get(k)
    if not v:
        return default
    return v.get("S") or v.get("N") or default


def _hhmmss(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%H:%M:%S")
    except Exception:
        return str(iso)[11:19]


def approval_requests(limit=25):
    r = _ddb().scan(TableName=APPROVAL_TABLE)
    reqs = []
    for it in r.get("Items", []):
        reqs.append({
            "request_id": _s(it, "request_id"),
            "action": _s(it, "action"),
            "description": _s(it, "description"),
            "sql": _s(it, "sql_statement"),
            "risk": _s(it, "risk_level"),
            "status": _s(it, "status"),
            "created_at": _s(it, "created_at"),
            "decided_at": _s(it, "decided_at"),
        })
    reqs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return reqs[:limit]


STATUS_MAP = {
    "pending": ("action", "Actions"), "approved": ("approval", "Supervisor"),
    "executed": ("success", "Actions"), "completed": ("success", "Actions"),
    "rejected": ("error", "Supervisor"), "denied": ("error", "Supervisor"),
}


def alerts():
    out = []
    try:
        series, cur = db.rds_cpu(10)
        if cur is not None:
            peak = max(series) if series else cur
            typ = "warning" if cur >= 80 else ("success" if cur < 50 else "info")
            out.append({"time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                        "type": typ, "agent": "Health",
                        "msg": "CPU " + str(cur) + "% (10-min peak " + str(peak) + "%)"})
    except Exception:
        pass
    try:
        for r in approval_requests(25):
            st = (r.get("status") or "").lower()
            typ, agent = STATUS_MAP.get(st, ("info", "Actions"))
            desc = r.get("description") or r.get("action") or "remediation"
            if len(desc) > 130:
                desc = desc[:130] + "..."
            out.append({"time": _hhmmss(r.get("decided_at") or r.get("created_at")),
                        "type": typ, "agent": agent, "msg": "[" + st + "] " + desc})
    except Exception as e:
        out.append({"time": "", "type": "error", "agent": "System",
                    "msg": "approval table unavailable: " + str(e)[:80]})
    return out


def _top_proc():
    sql = ("SELECT TOP 1 OBJECT_NAME(object_id) pn, "
           "total_worker_time/NULLIF(execution_count,0)/1000 avg_cpu_ms "
           "FROM sys.dm_exec_procedure_stats WHERE OBJECT_NAME(object_id) LIKE 'sp_%' "
           "ORDER BY total_worker_time DESC")
    rows, _ = db._run_db(db.TRAVELHUB_DB, sql)
    return rows[0] if rows else None


def remediation():
    reqs = approval_requests(25)
    latest = reqs[0] if reqs else None
    try:
        series, cur = db.rds_cpu(10)
    except Exception:
        series, cur = [], None
    peak = max(series) if series else cur
    steps = [{"step": "Think",
              "content": "CPU peaked at " + str(peak) + "% (now " + str(cur) + "%). Investigating top query consumers via procedure stats."}]
    try:
        tp = _top_proc()
        if tp:
            steps.append({"step": "Act",
                          "content": "Top consumer: " + str(tp["pn"]) + " at ~" + str(tp["avg_cpu_ms"]) + " ms/call CPU."})
    except Exception:
        pass
    if latest:
        steps.append({"step": "Observe", "content": latest.get("description") or "Analyzing execution plan."})
        steps.append({"step": "Evaluate",
                      "content": "Proposed " + str(latest.get("action")) + " (risk: " + str(latest.get("risk")) + "). Status: " + str(latest.get("status")) + "."})
        steps.append({"step": "Fix", "content": latest.get("sql") or "(no SQL statement)"})
    return {"steps": steps, "cpu_before": peak, "cpu_after": cur,
            "status": (latest or {}).get("status"), "request_id": (latest or {}).get("request_id")}
