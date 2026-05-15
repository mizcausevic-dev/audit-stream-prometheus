"""
audit-stream-prometheus — the other half of the audit-stream spine.

The seven producers in the Kinetic Gain implementation stack fan IN to
``audit-stream-py``. This service fans the same events back OUT to a
Prometheus scrape endpoint, so:

  * Existing Grafana / Prometheus stacks pick up governance events without
    any custom subscription code.
  * `decision_card_drafted_total`, `policy_request_denied_total`,
    `breaker_opened_total`, `slo_burn_started_total` etc. all show up as
    standard counter time series.
  * Per-source labels (`procurement-decision-api`, `policy-as-code-engine`,
    `reliability-toolkit`, ...) make it trivial to filter by which producer
    emitted what.

Closes the loop: audit-stream-py keeps the tamper-evident chain, this
service keeps the operational dashboards green.

Architecture
------------

::

    audit-stream-py    --SSE-->    audit-stream-prometheus    --scrape-->   Prometheus
       /events/stream                  /metrics                                |
                                                                               v
                                                                            Grafana
"""

from __future__ import annotations

from .bridge import EventBridge
from .metrics import event_counter, event_total

__version__ = "0.1.0"

__all__ = [
    "EventBridge",
    "__version__",
    "event_counter",
    "event_total",
]
