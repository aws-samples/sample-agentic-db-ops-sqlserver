"""
ReefShark Adventures - FastAPI backend.

Main-page search is powered entirely by plain TEXT SEARCH over the TravelHub
database on RDS SQL Server (Destinations, Flights, Hotels, Activities). No
semantic search, no TravelAI dependency.

Serving model (matches the original app contract):
  - Everything is served under /app on port 8081, behind the nginx `/app` -> :8081 proxy.
  - API routes are exposed under /app/api/... (matched before the static mount).
  - The Next.js static export (frontend/out) is served at /app for the UI.
"""
import os
import time
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from agent import TravelAgent
from mock_data import rental_cars

app = FastAPI(title="ReefShark Adventures", version="3.0.0")

# NOTE: open CORS for simple lab testing. Tighten allow_origins beyond a lab.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = TravelAgent()


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = "default"


@app.get("/app/status")
def root():
    return {"status": "ReefShark Adventures is running"}


@app.get("/app/api/health")
def health():
    """DB connectivity check (TravelHub)."""
    try:
        import db
        return db.health()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/app/api/metrics")
def api_metrics():
    """Live RDS CPU (CloudWatch) + SQL Server activity (DMVs) for the SRE dashboard."""
    import db, load
    try:
        m = db.metrics()
    except Exception as e:
        m = {"error": str(e), "cpu": {"current": None, "series": []},
             "qps": None, "blocking": None, "workers": None}
    try:
        m["load_running"] = load.running_count()
    except Exception:
        m["load_running"] = None
    return m


class LoadRequest(BaseModel):
    workers: int = 16
    scenarios: Optional[list] = None


@app.post("/app/api/load/start")
def load_start(req: LoadRequest):
    import load
    try:
        return load.start(req.workers)
    except Exception as e:
        return {"error": str(e)}


@app.post("/app/api/load/stop")
def load_stop():
    import load
    try:
        return load.stop()
    except Exception as e:
        return {"error": str(e)}


@app.get("/app/api/load/status")
def load_status():
    import load
    return {"running": load.running_count()}


@app.get("/app/api/alerts")
def api_alerts():
    import agentops
    try:
        return {"alerts": agentops.alerts()}
    except Exception as e:
        return {"alerts": [], "error": str(e)}


@app.get("/app/api/remediation")
def api_remediation():
    import agentops
    try:
        return agentops.remediation()
    except Exception as e:
        return {"steps": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Search tabs - all four backed by TravelHub text search.
# ---------------------------------------------------------------------------
@app.get("/app/api/search")
def api_search(q: str = "", topk: int = 8):
    """Destinations tab: text search over enriched TravelHub.Destinations."""
    import db
    try:
        results, ms = db.search_destinations(q, topk)
        return {"query": q, "results": results, "count": len(results),
                "latency_ms": ms, "source": "TravelHub.Destinations"}
    except Exception as e:
        return {"query": q, "results": [], "count": 0, "error": str(e)}


@app.get("/app/api/flights")
def search_flights(origin: str = "", destination: str = "",
                   date: str = "", return_date: str = "", topk: int = 8):
    """Flights tab: text search over TravelHub.Flights. Round-trip when return_date is set."""
    import db
    try:
        results, ms = db.th_flights(origin, destination, date, return_date, topk)
        return {"results": results, "count": len(results),
                "latency_ms": ms, "source": "TravelHub.Flights"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.get("/app/api/hotels")
def search_hotels(destination: str = "", checkin: str = "",
                  checkout: str = "", topk: int = 8):
    """Hotels tab: text search over TravelHub.Hotels."""
    import db
    try:
        results, ms = db.th_hotels(destination, checkin, checkout, topk)
        return {"results": results, "count": len(results),
                "latency_ms": ms, "source": "TravelHub.Hotels"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.get("/app/api/activities")
def search_activities(q: str = "", topk: int = 8):
    """Activities tab: text search over TravelHub.Activities."""
    import db
    try:
        results, ms = db.th_activities(q, topk)
        return {"results": results, "count": len(results),
                "latency_ms": ms, "source": "TravelHub.Activities"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.post("/app/api/chat")
def chat(msg: ChatMessage):
    """Agentic chat endpoint - the AI guides the user through travel planning."""
    return agent.process_message(msg.message, msg.session_id)


@app.get("/app/api/cars")
def search_cars(location: str = "Los Angeles", pickup_date: str = "2024-12-01"):
    results = [c for c in rental_cars if location.lower() in c["location"].lower()]
    if not results:
        results = rental_cars[:5]
    return {"results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Serve the Next.js static export under /app (mounted last so API wins).
# ---------------------------------------------------------------------------
from starlette.responses import JSONResponse

_FRONTEND_OUT = os.getenv(
    "FRONTEND_OUT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "out")),
)


@app.get("/")
def _root_redirect():
    return JSONResponse({"status": "ReefShark Adventures - open /app/"})


if os.path.isdir(_FRONTEND_OUT):
    app.mount("/app", StaticFiles(directory=_FRONTEND_OUT, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
