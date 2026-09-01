"""
TravelAI Agent Backend - FastAPI
Agentic travel booking assistant + real TravelAI hybrid search over RDS SQL Server 2025.

Serving model (matches the original Flask app contract):
  - Everything is served under /app on port 8081, behind the nginx `/app` -> :8081 proxy.
  - API routes are exposed under /app/api/... (the FastAPI `app` is mounted at /app).
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
from mock_data import flights, hotels, activities, rental_cars

app = FastAPI(title="TravelAI Agent", version="2.0.0")

# NOTE: open CORS for simple lab testing (frontend served from the EC2 public IP).
# Tighten allow_origins for anything beyond a throwaway lab.
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
    return {"status": "TravelAI Agent is running"}


@app.get("/app/api/health")
def health():
    """DB connectivity + embedding coverage check."""
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


# Static metadata for the 4 strategy cards (merged with live latency/count).
_STRATEGY_META = {
    "sql":      {"name": "SQL Baseline (WHERE)", "color": "slate",
                 "desc": "Pure WHERE clause on persisted JSON climate column"},
    "freetext": {"name": "Lexical (FREETEXT)", "color": "amber",
                 "desc": "SQL Server Full-Text Search with word stemming"},
    "semantic": {"name": "Semantic (VECTOR_DISTANCE)", "color": "purple",
                 "desc": "Cosine similarity via Bedrock Titan V2 1024-dim embeddings"},
    "hybrid":   {"name": "Hybrid (FTS + RAG)", "color": "emerald",
                 "desc": "FREETEXT + vector + DocumentChunks retrieval, RRF fusion"},
}


@app.get("/app/api/search")
def api_search(q: str = Query(..., min_length=1), topk: int = 5):
    """
    Run all four TravelAI retrieval strategies against RDS SQL Server, returning
    per-strategy latency + counts, the hybrid result set, and RAG document chunks.
    """
    import db

    strategies = {}
    results = []
    rag_chunks = []
    errors = {}

    runners = [
        ("sql", db.search_sql),
        ("freetext", db.search_freetext),
        ("semantic", db.search_vector),
        ("hybrid", db.search_hybrid),
    ]

    t_total = time.perf_counter()
    for key, fn in runners:
        meta = _STRATEGY_META[key]
        try:
            first, extra, ms = fn(q, topk)
            strategies[key] = {"name": meta["name"], "color": meta["color"],
                               "desc": meta["desc"], "latency": ms, "count": len(first)}
            if key == "hybrid":
                results = [db._norm_result(r) for r in first]
                if extra:
                    rag_chunks = [db._norm_chunk(r) for r in extra[0]]
        except Exception as e:
            errors[key] = str(e)
            strategies[key] = {"name": meta["name"], "color": meta["color"],
                               "desc": meta["desc"], "latency": None, "count": 0}
    total_ms = int((time.perf_counter() - t_total) * 1000)

    # Fallback: if hybrid failed, surface whichever strategy returned rows.
    if not results:
        for key, fn in runners:
            try:
                first, _, _ = fn(q, topk)
                if first:
                    results = [db._norm_result(r) for r in first]
                    break
            except Exception:
                continue

    winner = "hybrid" if strategies.get("hybrid", {}).get("count") else None

    return {
        "query": q,
        "strategies": strategies,
        "winner": winner,
        "results": results,
        "ragChunks": rag_chunks,
        "total_latency_ms": total_ms,
        "errors": errors,
    }


@app.post("/app/api/chat")
def chat(msg: ChatMessage):
    """Agentic chat endpoint - the AI guides the user through travel planning."""
    return agent.process_message(msg.message, msg.session_id)


@app.get("/app/api/flights")
def search_flights(origin: str = "", destination: str = "", topk: int = 8):
    """Live flights from TravelHub."""
    import db
    try:
        results, ms = db.th_flights(origin, destination, topk)
        return {"results": results, "count": len(results), "latency_ms": ms, "source": "TravelHub.Flights"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.get("/app/api/hotels")
def search_hotels(destination: str = "", topk: int = 8):
    """Live hotels from TravelHub."""
    import db
    try:
        results, ms = db.th_hotels(destination, topk)
        return {"results": results, "count": len(results), "latency_ms": ms, "source": "TravelHub.Hotels"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.get("/app/api/activities")
def search_activities(q: str = "", topk: int = 8):
    """Live activities from TravelHub."""
    import db
    try:
        results, ms = db.th_activities(q, topk)
        return {"results": results, "count": len(results), "latency_ms": ms, "source": "TravelHub.Activities"}
    except Exception as e:
        return {"results": [], "count": 0, "error": str(e)}


@app.get("/app/api/cars")
def search_cars(location: str = "Los Angeles", pickup_date: str = "2024-12-01"):
    results = [c for c in rental_cars if location.lower() in c["location"].lower()]
    if not results:
        results = rental_cars[:5]
    return {"results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# Serve under /app (same external contract as the original Flask app), on :8081.
#   - All API routes above are registered as real routes at /app/api/... and are
#     matched BEFORE the StaticFiles mount below (Starlette checks explicit
#     routes before a Mount), so the API always wins over the SPA catch-all.
#   - The Next.js static export (frontend/out) is mounted LAST at /app and serves
#     the UI + client-side routes (html=True resolves /app/ and /app/search/).
# ---------------------------------------------------------------------------
from starlette.responses import JSONResponse

# Path to the built Next.js static export (frontend/out). Overridable for local dev.
_FRONTEND_OUT = os.getenv(
    "FRONTEND_OUT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "out")),
)


@app.get("/")
def _root_redirect():
    return JSONResponse({"status": "ReefShark Adventures — open /app/"})


# Mount the SPA last so it acts as the fallback for any non-API /app path.
if os.path.isdir(_FRONTEND_OUT):
    app.mount("/app", StaticFiles(directory=_FRONTEND_OUT, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
