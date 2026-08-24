"""FastAPI dashboard for Aurel3 — read-only performance tracking.

Serves on 127.0.0.1:8082 behind the cloudflared tunnel at aurel3.clawdiu.org.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import metrics

app = FastAPI(title="Aurel3 Dashboard")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# The payload walks every buy-lane rec through yfinance; rebuilding it per
# request would make the page unusable and hammer the API.
_CACHE_TTL_SECONDS = 600
_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"at": 0.0, "payload": None}


def get_data(force: bool = False) -> dict:
    now = time.time()
    with _cache_lock:
        payload = _cache["payload"]
        if payload is not None and not force and now - _cache["at"] < _CACHE_TTL_SECONDS:
            return payload
    fresh = metrics.build_dashboard_data()
    with _cache_lock:
        _cache["at"] = time.time()
        _cache["payload"] = fresh
    return fresh


def _pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    return "{:+.{d}f}%".format(value * 100, d=digits)


def _money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return "${:,.2f}".format(value)


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "—"
    return "{:,.{d}f}".format(value, d=digits)


templates.env.filters["pct"] = _pct
templates.env.filters["money"] = _money
templates.env.filters["num"] = _num


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, action: str = "all", refresh: int = 0):
    data = get_data(force=bool(refresh))
    rows = data["recommendations"]

    if action == "buy":
        rows = [row for row in rows if row["is_buy_lane"]]
    elif action in ("buy_now", "early_accumulation", "watch_for_confirmation", "hold_not_fresh_buy"):
        rows = [row for row in rows if row["action"] == action]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "data": data,
            "rows": rows,
            "action": action,
            "scoreboard": data["scoreboard"],
            "cohort": data["scoreboard"]["cohort"],
            "equity": data["equity"],
            "themes": data["themes"],
            "outcomes": data["outcomes"],
            "ops": data["ops"],
        },
    )


@app.get("/api/summary")
async def api_summary(refresh: int = 0):
    data = get_data(force=bool(refresh))
    return {
        "scoreboard": data["scoreboard"],
        "ops": data["ops"],
        "generated_at": data["generated_at"],
    }


@app.get("/api/cohort")
async def api_cohort():
    return get_data()["scoreboard"]["cohort"]


@app.get("/api/equity")
async def api_equity():
    return get_data()["equity"]


@app.get("/api/themes")
async def api_themes():
    return get_data()["themes"]


@app.get("/api/recommendations")
async def api_recommendations(limit: int = 120):
    return get_data()["recommendations"][:limit]


@app.get("/healthz")
async def healthz():
    ops = get_data()["ops"]
    return {"ok": True, "last_batch_at": ops["last_batch_at"], "staleness": ops["staleness"]}
