"""
The SSE → Prometheus bridge loop.

``EventBridge.run()`` connects to ``{AUDIT_STREAM_URL}/events/stream``,
reads server-sent events forever, and increments the matching
``audit_stream_events_total`` counter for each one.

Reconnect strategy: exponential backoff with cap. Each reconnect resets
``bridge_up`` to 0 until the next event lands. Operators alerting on
``audit_stream_bridge_up == 0 for 1m`` will catch durable outages.

The event envelope this bridge expects matches what every producer in
the Kinetic Gain stack emits (procurement-decision-api,
aeo-validator-service, policy-as-code-engine, data-contract-registry,
slo-budget-tracker, hash-attestation, incident-correlation,
aeo-graph-explorer, reliability-toolkit):

::

    { "kind":    "decision_card_drafted",
      "source":  "procurement-decision-api",
      "payload": { ... } }

Only ``kind`` and ``source`` are used here; ``payload`` flows past
untouched (the tamper-evident chain in audit-stream-py is the canonical
home for full payloads).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from httpx_sse import aconnect_sse

from .metrics import bridge_up, event_counter

log = logging.getLogger("audit_stream_prometheus.bridge")


DEFAULT_BACKOFF_INITIAL_S = 0.5
DEFAULT_BACKOFF_MAX_S = 30.0


class EventBridge:
    """Long-running SSE consumer that increments Prometheus counters.

    Build one per process. The :meth:`run` coroutine blocks forever, so
    typically you ``asyncio.create_task`` it from FastAPI's lifespan.
    """

    def __init__(
        self,
        audit_stream_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        backoff_initial_s: float = DEFAULT_BACKOFF_INITIAL_S,
        backoff_max_s: float = DEFAULT_BACKOFF_MAX_S,
    ) -> None:
        self._url = audit_stream_url.rstrip("/")
        self._client = client
        self._owned_client = client is None
        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s
        self._stop = asyncio.Event()

    @property
    def stream_url(self) -> str:
        """Full SSE endpoint this bridge subscribes to."""
        return f"{self._url}/events/stream"

    async def run(self) -> None:
        """Subscribe and process events. Reconnects on failure forever
        unless :meth:`stop` is called."""
        client = self._client or httpx.AsyncClient(timeout=None)
        try:
            backoff = self._backoff_initial_s
            while not self._stop.is_set():
                try:
                    await self._consume(client)
                    backoff = self._backoff_initial_s  # reset after a clean stream
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    bridge_up.set(0)
                    log.warning(
                        "audit-stream SSE disconnect: %s: %s; retry in %.1fs",
                        type(err).__name__,
                        err,
                        backoff,
                    )
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                        break
                    except TimeoutError:
                        pass
                    backoff = min(backoff * 2, self._backoff_max_s)
        finally:
            if self._owned_client:
                await client.aclose()

    async def _consume(self, client: httpx.AsyncClient) -> None:
        async with aconnect_sse(client, "GET", self.stream_url) as source:
            bridge_up.set(1)
            async for sse in source.aiter_sse():
                if self._stop.is_set():
                    return
                self._handle_event(sse.data)

    def _handle_event(self, raw: str) -> None:
        """Increment the counter for one raw SSE payload.

        Silent on malformed JSON / missing fields — the bridge should
        never crash the dashboard pipeline because one producer emitted
        garbage. The counter just doesn't tick; operators see the gap.
        """
        try:
            event: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("dropping non-JSON SSE payload: %r", raw[:120])
            return
        kind = event.get("kind")
        source = event.get("source")
        if not isinstance(kind, str) or not isinstance(source, str):
            log.debug("dropping malformed event (missing kind/source): %r", event)
            return
        event_counter.labels(kind=kind, source=source).inc()

    def stop(self) -> None:
        """Signal the run loop to exit at the next chance."""
        self._stop.set()
