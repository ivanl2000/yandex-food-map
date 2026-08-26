#!/usr/bin/env python3
"""Yandex Food Map — FastAPI server with auto-update webhook."""
import logging
import os
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
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
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Helpers ──────────────────────────────────────────────────────────────

def _run_update():
    """Pull from GitHub via deploy script and signal restart."""
    script = Path(__file__).parent / "deploy.sh"
    if script.exists():
        logger.info("Running deploy script: %s", script)
        result = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=60)
        logger.info("deploy.sh stdout:\n%s", result.stdout)
        if result.stderr:
            logger.warning("deploy.sh stderr:\n%s", result.stderr)
        return result.returncode == 0, result.stdout
    return False, "deploy.sh not found"


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health-check endpoint. Also runs git fetch to detect stale state."""
    return {
        "status": "ok",
        "version": app.version,
        "orders_db": settings.db_path,
        "repo": _git_describe(),
    }


def _git_describe() -> dict:
    """Return current git sha and branch."""
    try:
        sha = subprocess.run(
            ["git", "-C", str(Path(__file__).parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(Path(__file__).parent), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return {"sha": sha, "branch": branch}
    except Exception:
        return {"sha": "unknown", "branch": "unknown"}


@app.post("/api/update", summary="Pull latest code and restart")
async def update(request: Request):
    """
    Webhook endpoint: call ``git pull`` and restart the server.

    Protected by a simple secret token passed via ``X-Update-Token`` header
    or query parameter ``token``. Set via ``YF_UPDATE_TOKEN`` env var.
    """
    token = os.environ.get("YF_UPDATE_TOKEN", "")

    # Check auth
    header_token = request.headers.get("X-Update-Token", "")
    query_token = request.query_params.get("token", "")
    if token and header_token != token and query_token != token:
        raise HTTPException(403, "Invalid or missing update token")

    success, output = _run_update()
    status_code = 200 if success else 500
    return JSONResponse(
        content={"success": success, "output": output[:2000]},
        status_code=status_code,
    )


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
    logger.info("Starting Yandex Food Map v%s — %s", app.version, _git_describe())
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()