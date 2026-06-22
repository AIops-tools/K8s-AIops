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


def call(fn: Callable[..., Any], *args: Any, path: str = "", **kwargs: Any) -> Any:
    """Invoke a kubernetes-client method, translating ApiException centrally."""
    try:
        return fn(*args, **kwargs)
    except ApiException as exc:
        raise translate_api_error(exc, path) from exc


def age_of(timestamp: Any) -> str:
    """Render a creation timestamp as a compact age string (e.g. '3d', '5m')."""
    if not timestamp:
        return ""
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
        return ""
