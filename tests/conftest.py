from __future__ import annotations

import pytest

from tool_call_tr.network import UrllibJsonTransport


@pytest.fixture(autouse=True)
def block_live_provider_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test reaches the default live HTTP transport."""

    def blocked_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("tests must inject a transport instead of using live provider network")

    monkeypatch.setattr(UrllibJsonTransport, "request_json", blocked_request)
