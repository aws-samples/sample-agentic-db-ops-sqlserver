"""
TravelHub data-access layer for the ReefShark main-page search.

All four search tabs (Destinations, Flights, Hotels, Activities) run plain
TEXT SEARCH against the TravelHub database on RDS SQL Server. There is NO
semantic search and NO dependency on the TravelAI database.

Search is a tokenized, case-insensitive LIKE across the relevant descriptive
columns (enriched by load_generator/travelhub/05_enrich_for_app_search.sql):
  - Destinations: DisplayName, Country, Continent, Climate, Season, Tags, Description
  - Flights:      OriginCity / DestCity (real city names)
  - Hotels:       City, HotelName, Amenities, Description
  - Activities:   ActivityName, Category, Tags, City, Description

Configuration via environment variables (with sane lab defaults):
  AWS_REGION      default us-west-2
  DB_SECRET_ID    default dbops-infra-sqlserver-secret
  TRAVELHUB_DB    default TravelHub
"""
import os
import re
import json
import time
import functools

import boto3
import pymssql

REGION = os.getenv("AWS_REGION", "us-west-2")
SECRET_ID = os.getenv("DB_SECRET_ID", "dbops-infra-sqlserver-secret")
TRAVELHUB_DB = os.getenv("TRAVELHUB_DB", "TravelHub")


@functools.lru_cache(maxsize=1)
def _creds():
    sm = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])


def get_conn_named(dbname=TRAVELHUB_DB):
    c = _creds()
    return pymssql.connect(
        server=c["host"], user=c["username"], password=c["password"],
        port=int(c["port"]), database=dbname, timeout=60, login_timeout=15,
    )


def _rows(cur):
    if not cur.description:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _run_db(sql, params=(), dbname=TRAVELHUB_DB):
    conn = get_conn_named(dbname)
    conn.autocommit(True)
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(sql, tuple(params))
    rows = _rows(cur)
    ms = int((time.perf_counter() - t0) * 1000)
    cur.close()
    conn.close()
    return rows, ms


# --- helpers ---------------------------------------------------------------

def _tokens(q, limit=6):
    """Split a free-text query into up to `limit` alphanumeric word tokens."""
    if not q:
        return []
    toks = re.findall(r"[A-Za-z0-9]+", q)
    # keep tokens of length >= 2 (drop noise like single letters)
    toks = [t for t in toks if len(t) >= 2] or toks
    return toks[:limit]


def _clause(cols, tokens):
    """
    Build an OR-of-tokens text-match clause. A row matches if ANY token is a
    substring of ANY of the given columns. Returns (sql_fragment, params).
    """
    if not tokens:
        return "1=1", []
    ors, params = [], []
    for t in tokens:
        per_col = " OR ".join(f"{c} LIKE %s" for c in cols)
        ors.append(f"({per_col})")
        params.extend([f"%{t}%"] * len(cols))
    # OR across tokens => broad recall (beach OR snorkeling ...)
    return "(" + " OR ".join(ors) + ")", params


def _clamp(topk, default=8, hi=50):
    try:
        k = int(topk)
    except (TypeError, ValueError):
        k = default
    return max(1, min(k, hi))


def _f(v):
    return float(v) if v is not None else None


def _nights(checkin, checkout, default=1):
    """Number of nights between two YYYY-MM-DD strings (>=1); default if invalid."""
    from datetime import date
    try:
        y1, m1, d1 = map(int, checkin.split("-"))
        y2, m2, d2 = map(int, checkout.split("-"))
        n = (date(y2, m2, d2) - date(y1, m1, d1)).days
        return n if n >= 1 else default
    except Exception:
        return default


# --- Destinations ----------------------------------------------------------

def search_destinations(q, topk=8):
    """Text search over enriched Destinations via usp_App_SearchDestinations."""
    k = _clamp(topk)
    rows, ms = _run_db("EXEC dbo.usp_App_SearchDestinations %s, %d", (q or "", k))
    out = [{
        "title": r["DisplayName"],
        "country": r["Country"],
        "continent": r["Continent"],
        "climate": r["Climate"],
        "season": r["Season"],
        "tags": r["Tags"],
        "snippet": r["Description"],
        "score": r["PopularityScore"],
    } for r in rows]
    return out, ms


# --- Flights ---------------------------------------------------------------

def _flight_leg(origin, destination, depart_date, k):
    return _run_db(
        "EXEC dbo.usp_App_SearchFlights %s, %s, %s, %d",
        (origin or "", destination or "", depart_date or None, k))


def _fmt_flight(r, leg):
    return {
        "leg": leg,
        "airline": r["Airline"], "flightNumber": r["FlightNumber"],
        "origin": r["OriginCity"] or r["Origin"], "destination": r["DestCity"] or r["Destination"],
        "departDate": r["DepartDate"], "departTime": r["DepartTime"], "arriveTime": r["ArriveTime"],
        "durationMinutes": r["DurationMinutes"], "price": _f(r["Price"]),
        "seats": r["SeatsAvailable"], "aircraft": r["Aircraft"],
    }


def th_flights(origin="", destination="", depart_date="", return_date="", topk=8):
    """
    Flight text search over TravelHub.Flights. If return_date is supplied a
    round-trip is returned: outbound (origin -> destination, on/after the
    departure date) plus the return leg (destination -> origin, on/after the
    return date). Each row is tagged via the `leg` field ("Outbound"/"Return").
    """
    k = _clamp(topk)
    rows_out, ms = _flight_leg(origin, destination, depart_date, k)
    out = [_fmt_flight(r, "Outbound") for r in rows_out]
    if return_date:
        rows_ret, ms2 = _flight_leg(destination, origin, return_date, k)
        out += [_fmt_flight(r, "Return") for r in rows_ret]
        ms += ms2
    return out, ms


# --- Hotels ----------------------------------------------------------------

def th_hotels(destination="", checkin="", checkout="", topk=8):
    """
    Hotel text search by city / name / amenities. When check-in and check-out
    are supplied, the number of nights and the total stay price (nights x
    nightly rate) are computed. TravelHub has no per-night availability table,
    so all text matches are treated as available for the requested dates.
    """
    k = _clamp(topk)
    have_dates = bool(checkin and checkout)
    nights = _nights(checkin, checkout) if have_dates else None
    rows, ms = _run_db("EXEC dbo.usp_App_SearchHotels %s, %d", (destination or "", k))
    out = []
    for r in rows:
        price = _f(r["PricePerNight"])
        out.append({
            "name": r["HotelName"], "city": r["City"], "country": r["Country"],
            "stars": r["StarRating"], "price": price,
            "review": _f(r["ReviewScore"]), "amenities": r["Amenities"],
            "checkin": checkin or None, "checkout": checkout or None,
            "nights": nights,
            "total": round(price * nights, 2) if (price is not None and nights) else None,
        })
    return out, ms


# --- Activities ------------------------------------------------------------

def th_activities(q="", topk=8):
    k = _clamp(topk)
    rows, ms = _run_db("EXEC dbo.usp_App_SearchActivities %s, %d", (q or "", k))
    out = [{
        "name": r["ActivityName"], "category": r["Category"], "tags": r["Tags"],
        "city": r["City"], "country": r["Country"], "price": _f(r["Price"]),
        "duration": _f(r["DurationHours"]), "difficulty": r["DifficultyLevel"],
    } for r in rows]
    return out, ms


# --- health ----------------------------------------------------------------

def health():
    """Lightweight connectivity + data check against TravelHub."""
    rows, ms = _run_db(
        "SELECT COUNT(*) AS destinations, COUNT(DISTINCT DisplayName) AS cities "
        "FROM dbo.Destinations")
    row = rows[0] if rows else {}
    return {"ok": True, "latency_ms": ms, "destinations": row.get("destinations"),
            "cities": row.get("cities"), "database": TRAVELHUB_DB}


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
        Namespace="AWS/RDS", MetricName="CPUUtilization",
        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": RDS_INSTANCE_ID}],
        StartTime=now - timedelta(minutes=minutes), EndTime=now,
        Period=60, Statistics=["Average"],
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
            "WHERE is_user_process = 1 AND database_id = DB_ID(%s)", (TRAVELHUB_DB,))
        sessions = cur.fetchone()[0]
        counter_sql = ("SELECT cntr_value FROM sys.dm_os_performance_counters "
                       "WHERE counter_name = 'Batch Requests/sec'")
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
        "qps": act.get("qps"), "blocking": act.get("blocking"),
        "workers": act.get("sessions"), "error": act.get("error"),
    }
