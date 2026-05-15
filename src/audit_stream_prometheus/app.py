"""
FastAPI app with three endpoints:

  GET  /          service info
  GET  /healthz   liveness probe (reports bridge_up gauge value)
  GET  /metrics   Prometheus scrape endpoint

The SSE consumer is started as a background task in the lifespan and
runs forever. Restarting the process reconnects to audit-stream-py.

Config (env vars):
    AUDIT_STREAM_URL    base URL of audit-stream-py (required)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from . import __version__
from .bridge import EventBridge
from .metrics import bridge_up, render


def _audit_stream_url() -> str:
    raw = os.environ.get("AUDIT_STREAM_URL", "").strip()
    if not raw:
        raise RuntimeError(
            "AUDIT_STREAM_URL is required — point this service at your "
            "audit-stream-py instance, e.g. http://audit-stream:8093"
        )
    return raw.rstrip("/")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    bridge = EventBridge(_audit_stream_url())
    app.state.bridge = bridge
    task = asyncio.create_task(bridge.run(), name="audit-stream-sse-consumer")
    try:
        yield
    finally:
        bridge.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(
    title="audit-stream-prometheus",
    version=__version__,
    description=(
        "Bridges audit-stream-py SSE feed to a Prometheus scrape endpoint. "
        "The consumer half of the Kinetic Gain audit-stream spine."
    ),
    lifespan=_lifespan,
)


@app.get("/", tags=["meta"])
async def root() -> dict[str, Any]:
    bridge: EventBridge = app.state.bridge
    return {
        "name": "audit-stream-prometheus",
        "version": __version__,
        "description": (
            "Subscribes to audit-stream-py's SSE feed and re-exposes every "
            "governance event as a Prometheus counter."
        ),
        "upstream_sse": bridge.stream_url,
        "endpoints": {
            "GET  /": "this page",
            "GET  /healthz": "liveness probe",
            "GET  /metrics": "Prometheus scrape endpoint",
        },
    }


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, Any]:
    up = _gauge_value(bridge_up) == 1.0
    if not up:
        # Report 503 only when the bridge has explicitly dropped — fresh
        # start is also 0 but the SSE consumer will flip it within a
        # round trip.
        raise HTTPException(status_code=503, detail={"status": "bridge_down"})
    return {"status": "ok", "bridge_up": True}


@app.get("/metrics", tags=["metrics"])
async def metrics() -> Response:
    body, content_type = render()
    return Response(content=body, media_type=content_type)


def _gauge_value(g: Any) -> float:
    """Return the current value of a single-series Gauge (no labels)."""
    return float(g._value.get())
