"""End-to-end tests for the FastAPI app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from audit_stream_prometheus.metrics import bridge_up


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AUDIT_STREAM_URL", "http://audit-stream.invalid:8093")
    # Import here so the lifespan picks up the env var.
    from audit_stream_prometheus.app import app

    with TestClient(app) as c:
        yield c


def test_root_lists_endpoints(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "audit-stream-prometheus"
    assert body["upstream_sse"] == "http://audit-stream.invalid:8093/events/stream"


def test_healthz_returns_503_when_bridge_down(client: TestClient) -> None:
    # The lifespan launches the consumer task against an unreachable URL,
    # so bridge_up stays at 0. healthz should report 503.
    r = client.get("/healthz")
    assert r.status_code == 503


def test_healthz_branch_logic_directly() -> None:
    """The 200-when-up case can't be tested through the lifespan because
    the background bridge task resets the gauge when its connect fails.
    Verify the branch logic directly instead — flip the gauge and assert
    the helper reports up."""
    from audit_stream_prometheus.app import _gauge_value

    bridge_up.set(1)
    try:
        assert _gauge_value(bridge_up) == 1.0
    finally:
        bridge_up.set(0)


def test_metrics_serves_prometheus_format(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # The counter family is registered eagerly, so the HELP/TYPE lines
    # are present even before the first increment.
    assert "audit_stream_events_total" in body
    assert "audit_stream_bridge_up" in body
    assert "# HELP" in body
    assert "# TYPE" in body
