"""
Prometheus metric definitions.

Single counter family: ``audit_stream_events_total{kind, source}``.

Why one counter, not one per event kind:

  * Cardinality stays bounded — even with the full Kinetic Gain producer
    set, you cap at (~20 event kinds) x (~10 sources) = ~200 series. That's
    well under typical per-target limits.
  * New producers/event kinds light up automatically — no code change here,
    no Prometheus config change, the new series just appears.
  * Easier to write a Grafana panel that filters "all denies across all
    producers" with one ``rate(audit_stream_events_total{kind=~".*_denied|.*_failed"}[5m])``.

A separate ``audit_stream_bridge_up`` gauge reports SSE connectivity so
operators know whether the bridge is talking to audit-stream-py.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, generate_latest

# Module-level registry so tests can build a fresh one when needed.
REGISTRY = CollectorRegistry()

event_counter = Counter(
    "audit_stream_events_total",
    "Count of audit-stream governance events observed, by kind + source.",
    labelnames=("kind", "source"),
    registry=REGISTRY,
)

bridge_up = Gauge(
    "audit_stream_bridge_up",
    "1 when this bridge is actively receiving from audit-stream-py; 0 otherwise.",
    registry=REGISTRY,
)

# Bridge starts down — flipped by EventBridge.run() on first connect.
bridge_up.set(0)


def event_total(kind: str, source: str) -> float:
    """Helper for tests — current value of the counter at (kind, source)."""
    sample = event_counter.labels(kind=kind, source=source)._value.get()
    return float(sample)


def render() -> tuple[bytes, str]:
    """Render the current registry in Prometheus text-exposition format."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
