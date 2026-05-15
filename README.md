# audit-stream-prometheus

> The other half of the audit-stream spine. Producers fan IN to
> [`audit-stream-py`](https://github.com/mizcausevic-dev/audit-stream-py);
> this service fans the same events back OUT to a Prometheus scrape endpoint.

[![CI](https://github.com/mizcausevic-dev/audit-stream-prometheus/actions/workflows/ci.yml/badge.svg)](https://github.com/mizcausevic-dev/audit-stream-prometheus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/audit-stream-prometheus.svg)](https://pypi.org/project/audit-stream-prometheus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## What it does

`audit-stream-py` keeps a hash-chained, tamper-evident log of every governance
moment the Kinetic Gain implementation stack produces — Decision Cards drafted,
policy bundles registered, requests denied, contracts broken, signatures
verified, breakers tripped, SLO budgets burning. Every event is timestamped,
signed into the chain, and queryable via REST.

That's perfect for compliance and after-the-fact replay. It's the wrong shape
for the dashboards your SRE team already runs.

This service closes the loop:

```
audit-stream-py    --SSE-->    audit-stream-prometheus    --scrape-->   Prometheus
   /events/stream                  /metrics                                |
                                                                           v
                                                                        Grafana
```

One process. One SSE subscription. One scrape endpoint. Every event kind from
every producer in the stack becomes a regular Prometheus counter time series.

## What you get on `/metrics`

```
# HELP audit_stream_events_total Count of audit-stream governance events observed, by kind + source.
# TYPE audit_stream_events_total counter
audit_stream_events_total{kind="decision_card_drafted",source="procurement-decision-api"} 412
audit_stream_events_total{kind="policy_bundle_registered",source="policy-as-code-engine"} 47
audit_stream_events_total{kind="request_allowed",source="policy-as-code-engine"} 1893421
audit_stream_events_total{kind="request_denied",source="policy-as-code-engine"} 1284
audit_stream_events_total{kind="contract_compatibility_failed",source="data-contract-registry"} 7
audit_stream_events_total{kind="breaker_opened",source="reliability-toolkit"} 3
audit_stream_events_total{kind="slo_burn_started",source="slo-budget-tracker"} 1
audit_stream_events_total{kind="attestation_failed",source="hash-attestation"} 2
...

# HELP audit_stream_bridge_up 1 when this bridge is actively receiving from audit-stream-py; 0 otherwise.
# TYPE audit_stream_bridge_up gauge
audit_stream_bridge_up 1
```

One counter family, two labels (`kind`, `source`). Bounded cardinality even with
the full Kinetic Gain producer roster — ~20 event kinds × ~10 sources = ~200
series. New producers and event kinds appear automatically; no config change here.

## Useful queries

```promql
# Total denies across all enforcement points in the last 5 minutes
rate(audit_stream_events_total{kind=~"request_denied|attestation_failed|contract_compatibility_failed"}[5m])

# Per-producer event throughput
sum by (source) (rate(audit_stream_events_total[5m]))

# Anything currently in a "we lost trust" state
sum by (kind) (rate(audit_stream_events_total{kind=~".*_failed|breaker_opened|slo_burn_started"}[5m]))

# Alert: no governance events flowing for 5 minutes
absent_over_time(audit_stream_events_total[5m])

# Alert: bridge has been down for over a minute
audit_stream_bridge_up == 0
```

## Install + run

```bash
pip install audit-stream-prometheus
AUDIT_STREAM_URL=http://audit-stream:8093 audit-stream-prometheus
```

Defaults to `:9091`. Override with `PORT` / `HOST`.

Container-friendly:

```dockerfile
FROM python:3.13-slim
RUN pip install audit-stream-prometheus
ENV PORT=9091
CMD ["audit-stream-prometheus"]
```

## Operational notes

- **Reconnect**: the SSE consumer reconnects with exponential backoff
  (0.5s → 30s cap). The `audit_stream_bridge_up` gauge flips to 0 the
  moment the connection drops and back to 1 once SSE reconnects.
- **Crash safety**: malformed events (bad JSON, missing `kind` / `source`)
  are silently dropped — the bridge should never poison the dashboard
  pipeline because one producer emitted garbage. Operators see gaps in
  the counter rather than hard failures.
- **Payload privacy**: only `kind` and `source` are exposed to Prometheus.
  Event `payload` content stays in audit-stream-py's tamper-evident chain
  where it belongs.

## Composes with

- **[audit-stream-py](https://github.com/mizcausevic-dev/audit-stream-py)** — the upstream this service subscribes to.
- **All seven Kinetic Gain producers** — every one's `kind`/`source` envelope follows the same convention, so they all "just work" without per-producer config:
  - `procurement-decision-api` · `aeo-validator-service` · `policy-as-code-engine` · `data-contract-registry` · `slo-budget-tracker` (Python · FastAPI)
  - `hash-attestation` · `incident-correlation` · `aeo-graph-explorer` · `reliability-toolkit` (Rust)

## License

MIT. See [LICENSE](LICENSE).
