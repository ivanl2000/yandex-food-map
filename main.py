#!/usr/bin/env python3
"""Yandex Food Map — FastAPI server with Leaflet frontend."""
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# Search module
from search import search  # noqa: E402

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("yf.server")

# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Yandex Food Map",
    description="Map-based search over Yandex Food orders",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health-check endpoint."""
    return {"status": "ok", "orders_db": settings.db_path}


@app.get("/api/search", summary="Search orders")
async def search_orders(
    q: str = Query("", min_length=2, max_length=100, description="Search query (phone, name, city, place)"),
    limit: int = Query(200, ge=1, le=1000, description="Max results"),
):
    """
    Full-text search across Yandex Food orders.

    Heuristics detect phone numbers vs names vs addresses automatically.
    Uses SQLite B-tree range queries (no LIKE) for speed.
    """
    if not q.strip():
        raise HTTPException(400, "Query string is required")

    results = search(q, limit=limit)
    return {"total": len(results), "results": results}


@app.get("/", include_in_schema=False)
async def index():
    """Serve the Leaflet map front-end."""
    html_path = Path(__file__).parent / "index.html"
    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(html)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting Yandex Food Map on %s:%d", settings.host, settings.port)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()