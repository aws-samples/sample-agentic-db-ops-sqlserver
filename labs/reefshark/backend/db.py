"""
TravelAI database access layer.

Connects to the private RDS SQL Server (via Secrets Manager creds) and calls the
TravelAI search stored procedures:
  - usp_SearchSQL       (pure WHERE-clause baseline)
  - usp_SearchFreetext  (SQL Server Full-Text Search)
  - usp_SearchVector    (semantic search via VECTOR_DISTANCE + Bedrock embedding)
  - usp_HybridSearch    (RRF fusion of vector + full-text, plus RAG doc chunks)

Configuration via environment variables (with sane lab defaults):
  AWS_REGION      default us-east-1
  DB_SECRET_ID    default dbops-infra-sqlserver-secret
  TRAVELAI_DB     default TravelAI
"""
import os
import json
import time
import functools

import boto3
import pymssql

REGION = os.getenv("AWS_REGION", "us-east-1")
SECRET_ID = os.getenv("DB_SECRET_ID", "dbops-infra-sqlserver-secret")
DB_NAME = os.getenv("TRAVELAI_DB", "TravelAI")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bedrock_embed")


@functools.lru_cache(maxsize=1)
def _creds():
    sm = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])


def get_conn():
    c = _creds()
    return pymssql.connect(
        server=c["host"],
        user=c["username"],
        password=c["password"],
        port=int(c["port"]),
        database=DB_NAME,
        timeout=60,
        login_timeout=15,
    )


def _rows(cur):
    if not cur.description:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _run(sql, params=()):
    """Execute a statement, return (first_result_set, [extra_result_sets], elapsed_ms)."""
    conn = get_conn()
    conn.autocommit(True)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    first = _rows(cur)
    extra = []
    while cur.nextset():
        extra.append(_rows(cur))
    ms = int((time.perf_counter() - t0) * 1000)
    cur.close()
    conn.close()
    return first, extra, ms


# --- individual strategies -------------------------------------------------

def search_sql(q, topk=5):
    return _run("EXEC usp_SearchSQL %s, %d", (q, topk))


def search_freetext(q, topk=5):
    return _run("EXEC usp_SearchFreetext %s, %d", (q, topk))


def search_vector(q, topk=5):
    # Generate the query embedding server-side, then run the vector proc.
    sql = (
        "DECLARE @v VECTOR(1024) = AI_GENERATE_EMBEDDINGS(%s USE MODEL " + EMBED_MODEL + "); "
        "EXEC usp_SearchVector @v, %d"
    )
    return _run(sql, (q, topk))


def search_hybrid(q, topk=5):
    return _run("EXEC usp_HybridSearch %s, %d", (q, topk))


# --- normalization ---------------------------------------------------------

def _norm_result(row):
    """Map a destination row (varies slightly by proc) to a stable shape."""
    def g(*names):
        for n in names:
            if n in row and row[n] is not None:
                return row[n]
        return None
    score = g("RRFScore", "RelevanceScore", "popularity_score")
    try:
        score = round(float(score), 4) if score is not None else None
    except (TypeError, ValueError):
        pass
    return {
        "title": g("Title", "name"),
        "country": g("Country", "country_code"),
        "continent": g("Continent", "region"),
        "climate": g("Climate", "climate"),
        "season": g("Season", "best_season"),
        "snippet": g("Snippet", "description"),
        "score": score,
    }


def _norm_chunk(row):
    return {
        "source": row.get("Title") or row.get("section_path") or "Document",
        "snippet": row.get("Snippet") or row.get("content") or "",
    }


TRAVELHUB_DB = os.getenv("TRAVELHUB_DB", "TravelHub")


def get_conn_named(dbname):
    c = _creds()
    return pymssql.connect(
        server=c["host"], user=c["username"], password=c["password"],
        port=int(c["port"]), database=dbname, timeout=60, login_timeout=15,
    )


def _run_db(dbname, sql, params=()):
    conn = get_conn_named(dbname)
    conn.autocommit(True)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, params)
    rows = _rows(cur)
    ms = int((time.perf_counter() - t0) * 1000)
    cur.close()
    conn.close()
    return rows, ms


# --- TravelHub (relational OLTP data) queries ------------------------------

def th_hotels(dest, topk=8):
    like = f"%{dest}%" if dest else "%"
    sql = (
        "SELECT TOP (%d) h.HotelName, d.CityName, d.Country, h.StarRating, "
        "h.PricePerNight, h.ReviewScore "
        "FROM Hotels h JOIN Destinations d ON h.DestinationID = d.DestinationID "
        "WHERE d.CityName LIKE %s "
        "ORDER BY h.ReviewScore DESC, h.PricePerNight ASC"
    )
    rows, ms = _run_db(TRAVELHUB_DB, sql, (topk, like))
    return [{
        "name": r["HotelName"], "city": r["CityName"], "country": r["Country"],
        "stars": r["StarRating"], "price": float(r["PricePerNight"]) if r["PricePerNight"] is not None else None,
        "review": float(r["ReviewScore"]) if r["ReviewScore"] is not None else None,
    } for r in rows], ms


def th_flights(origin, destination, topk=8):
    sql = ("SELECT TOP (%d) Airline, FlightNumber, Origin, Destination, "
           "DepartDate, Price, SeatsAvailable FROM Flights")
    conds, params = [], [topk]
    if origin:
        conds.append("Origin LIKE %s"); params.append(origin.replace(" ", "")[:3] + "%")
    if destination:
        conds.append("Destination LIKE %s"); params.append(destination.replace(" ", "")[:3] + "%")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY Price ASC"
    rows, ms = _run_db(TRAVELHUB_DB, sql, tuple(params))
    return [{
        "airline": r["Airline"], "flightNumber": r["FlightNumber"],
        "origin": r["Origin"], "destination": r["Destination"],
        "departDate": str(r["DepartDate"])[:10] if r["DepartDate"] is not None else None,
        "price": float(r["Price"]) if r["Price"] is not None else None,
        "seats": r["SeatsAvailable"],
    } for r in rows], ms


def th_activities(q, topk=8):
    like = f"%{q}%" if q else "%"
    sql = (
        "SELECT TOP (%d) a.ActivityName, d.CityName, d.Country, a.Price, "
        "a.DurationHours, a.DifficultyLevel "
        "FROM Activities a JOIN Destinations d ON a.DestinationID = d.DestinationID "
        "WHERE a.ActivityName LIKE %s OR d.CityName LIKE %s "
        "ORDER BY a.Price ASC"
    )
    rows, ms = _run_db(TRAVELHUB_DB, sql, (topk, like, like))
    return [{
        "name": r["ActivityName"], "city": r["CityName"], "country": r["Country"],
        "price": float(r["Price"]) if r["Price"] is not None else None,
        "duration": float(r["DurationHours"]) if r["DurationHours"] is not None else None,
        "difficulty": r["DifficultyLevel"],
    } for r in rows], ms


# --- live SRE metrics (RDS CloudWatch CPU + SQL Server DMVs) ----------------

RDS_INSTANCE_ID = os.getenv("RDS_INSTANCE_ID", "dbops-infra-sqlserver")


@functools.lru_cache(maxsize=1)
def _cw():
    return boto3.client("cloudwatch", region_name=REGION)


def rds_cpu(minutes=10):
    """Return (series, current) of RDS CPUUtilization averages, oldest to newest."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    resp = _cw().get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": RDS_INSTANCE_ID}],
        StartTime=now - timedelta(minutes=minutes),
        EndTime=now,
        Period=60,
        Statistics=["Average"],
    )
    pts = sorted(resp.get("Datapoints", []), key=lambda d: d["Timestamp"])
    series = [round(p["Average"], 1) for p in pts]
    current = series[-1] if series else None
    return series, current


def sql_activity():
    """Blocking sessions, active user sessions, and batch requests/sec (1s sample)."""
    conn = get_conn_named(TRAVELHUB_DB)
    conn.autocommit(True)
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id <> 0")
        blocking = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM sys.dm_exec_sessions "
            "WHERE is_user_process = 1 AND database_id = DB_ID(%s)",
            (TRAVELHUB_DB,),
        )
        sessions = cur.fetchone()[0]

        # Batch Requests/sec is a cumulative counter - sample twice ~1s apart.
        counter_sql = (
            "SELECT cntr_value FROM sys.dm_os_performance_counters "
            "WHERE counter_name = 'Batch Requests/sec'"
        )
        cur.execute(counter_sql); v1 = cur.fetchone()[0]; t1 = time.perf_counter()
        time.sleep(1.0)
        cur.execute(counter_sql); v2 = cur.fetchone()[0]; t2 = time.perf_counter()
        qps = max(0, int((v2 - v1) / (t2 - t1)))
        return {"blocking": blocking, "sessions": sessions, "qps": qps}
    finally:
        cur.close()
        conn.close()


def metrics():
    """Consolidated live metrics for the SRE dashboard."""
    series, current = rds_cpu(10)
    act = {"blocking": None, "sessions": None, "qps": None}
    try:
        act = sql_activity()
    except Exception as e:
        act["error"] = str(e)
    return {
        "instance": RDS_INSTANCE_ID,
        "cpu": {"current": current, "series": series},
        "qps": act.get("qps"),
        "blocking": act.get("blocking"),
        "workers": act.get("sessions"),
        "error": act.get("error"),
    }


def health():
    """Lightweight connectivity + data check."""
    first, _, ms = _run(
        "SELECT COUNT(*) AS destinations, "
        "SUM(CASE WHEN description_vector IS NOT NULL THEN 1 ELSE 0 END) AS embedded "
        "FROM Destinations"
    )
    row = first[0] if first else {}
    return {"ok": True, "latency_ms": ms, "destinations": row.get("destinations"),
            "embedded": row.get("embedded"), "database": DB_NAME}
