"""Shared helpers for the ops layer: API-error translation and age formatting.

Every ops body calls the Kubernetes API through ``call()`` so that
``ApiException``s become teaching ``K8sApiError``s centrally instead of raw
tracebacks reaching the agent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from kubernetes.client.exceptions import ApiException

from k8s_aiops.connection import translate_api_error

# Default network timeout (seconds) for every Kubernetes API call. Without it
# the client can hang indefinitely on an unresponsive apiserver; callers may
# still pass an explicit ``_request_timeout`` to override per call.
_REQUEST_TIMEOUT = 30


def call(fn: Callable[..., Any], *args: Any, path: str = "", **kwargs: Any) -> Any:
    """Invoke a kubernetes-client method, translating ApiException centrally.

    Applies the default ``_request_timeout`` unless the caller provided one.
    """
    kwargs.setdefault("_request_timeout", _REQUEST_TIMEOUT)
    try:
        return fn(*args, **kwargs)
    except ApiException as exc:
        raise translate_api_error(exc, path) from exc


def age_of(timestamp: Any) -> str | None:
    """Render a creation timestamp as a compact age string (e.g. '3d', '5m').

    Returns ``None`` — not ``""`` — when the timestamp is absent or unparseable:
    "this object has no age we could read" is a different fact from an empty
    string, and a consumer must be able to tell them apart.
    """
    if not timestamp:
        return None
    try:
        if isinstance(timestamp, str):
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        return f"{secs // 86400}d"
    except (ValueError, TypeError):
        return None
