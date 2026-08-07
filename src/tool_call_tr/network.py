"""Small injectable JSON HTTP transport with normalized operational failures."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NetworkError(RuntimeError):
    pass


class NetworkTimeout(NetworkError):
    pass


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    status_code: int
    body: Any
    headers: Mapping[str, str]


class JsonTransport(Protocol):
    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        ...


class UrllibJsonTransport:
    """Standard-library transport; callers remain responsible for endpoint policy."""

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: Any | None,
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(url=url, data=payload, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL policy is enforced by callers
                raw = response.read()
                return JsonHttpResponse(response.status, _decode_body(raw), dict(response.headers.items()))
        except HTTPError as exc:
            return JsonHttpResponse(exc.code, _decode_body(exc.read()), dict(exc.headers.items()))
        except (TimeoutError, socket.timeout) as exc:
            raise NetworkTimeout("HTTP request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise NetworkTimeout("HTTP request timed out") from exc
            raise NetworkError(f"HTTP request failed: {type(exc.reason).__name__}") from exc


def _decode_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError("HTTP response is not valid UTF-8 JSON") from exc
