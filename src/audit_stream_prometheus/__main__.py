"""``python -m audit_stream_prometheus`` entry point.

Starts uvicorn on PORT (default 9091, the Prometheus pushgateway default
neighbour) so a `kubectl port-forward` or local `pip install` user has a
sane default without env-var setup.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn  # imported here so `--help` etc. on the CLI don't pay the cost

    port = int(os.environ.get("PORT", "9091"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("audit_stream_prometheus.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
