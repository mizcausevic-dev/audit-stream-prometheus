"""Tests for the SSE -> Prometheus bridge.

We don't run a real audit-stream-py server; we feed the bridge's
``_handle_event`` method synthetic raw SSE payload strings and assert
the counter ticks.
"""

from __future__ import annotations

import pytest

from audit_stream_prometheus.bridge import EventBridge
from audit_stream_prometheus.metrics import event_total


@pytest.fixture
def bridge() -> EventBridge:
    return EventBridge("http://audit.local:8093")


class TestHandleEvent:
    def test_known_event_increments_counter(self, bridge: EventBridge) -> None:
        before = event_total("decision_card_drafted", "procurement-decision-api")
        bridge._handle_event(
            '{"kind":"decision_card_drafted","source":"procurement-decision-api","payload":{}}'
        )
        after = event_total("decision_card_drafted", "procurement-decision-api")
        assert after == before + 1.0

    def test_multiple_increments_accumulate(self, bridge: EventBridge) -> None:
        before = event_total("breaker_opened", "reliability-toolkit")
        for _ in range(5):
            bridge._handle_event('{"kind":"breaker_opened","source":"reliability-toolkit","payload":{}}')
        after = event_total("breaker_opened", "reliability-toolkit")
        assert after == before + 5.0

    def test_independent_kinds_track_independently(self, bridge: EventBridge) -> None:
        before_a = event_total("policy_bundle_registered", "policy-as-code-engine")
        before_b = event_total("request_denied", "policy-as-code-engine")
        bridge._handle_event(
            '{"kind":"policy_bundle_registered","source":"policy-as-code-engine","payload":{}}'
        )
        bridge._handle_event('{"kind":"request_denied","source":"policy-as-code-engine","payload":{}}')
        bridge._handle_event('{"kind":"request_denied","source":"policy-as-code-engine","payload":{}}')
        assert event_total("policy_bundle_registered", "policy-as-code-engine") == before_a + 1.0
        assert event_total("request_denied", "policy-as-code-engine") == before_b + 2.0

    def test_malformed_json_is_silently_dropped(self, bridge: EventBridge) -> None:
        before = event_total("decision_card_drafted", "procurement-decision-api")
        bridge._handle_event("not valid json at all")
        bridge._handle_event("")
        bridge._handle_event("{}")
        after = event_total("decision_card_drafted", "procurement-decision-api")
        assert after == before

    def test_missing_kind_is_dropped(self, bridge: EventBridge) -> None:
        bridge._handle_event('{"source":"x","payload":{}}')
        # No assertion needed — just must not raise.

    def test_missing_source_is_dropped(self, bridge: EventBridge) -> None:
        bridge._handle_event('{"kind":"x","payload":{}}')

    def test_non_string_fields_are_dropped(self, bridge: EventBridge) -> None:
        bridge._handle_event('{"kind":123,"source":["wrong","type"],"payload":{}}')


class TestStreamUrl:
    def test_url_strips_trailing_slash(self) -> None:
        b = EventBridge("http://audit.local:8093/")
        assert b.stream_url == "http://audit.local:8093/events/stream"

    def test_url_already_clean(self) -> None:
        b = EventBridge("http://audit.local:8093")
        assert b.stream_url == "http://audit.local:8093/events/stream"
