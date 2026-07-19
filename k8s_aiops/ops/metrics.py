"""Read-only resource-usage operations via the metrics.k8s.io API (``top``).

These require a running metrics-server (CustomObjectsApi against
``metrics.k8s.io/v1beta1``). When it is absent the API returns 404/503; we catch
that and return a clear ``available: False`` message instead of crashing — a
``top`` query must never take down the agent just because metrics-server is not
installed. Other API errors are still translated centrally.
"""

from __future__ import annotations

from typing import Any

from kubernetes.client.exceptions import ApiException

from k8s_aiops.connection import translate_api_error
from k8s_aiops.governance import opt_str
from k8s_aiops.ops._shared import _REQUEST_TIMEOUT

_GROUP = "metrics.k8s.io"
_VERSION = "v1beta1"
_ABSENT_CODES = (404, 503)
_ABSENT_MSG = (
    "metrics-server is not installed or not reachable. Install metrics-server "
    "(https://github.com/kubernetes-sigs/metrics-server) to use 'top'."
)


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _absent(detail: str | None = None) -> dict:
    return {"available": False, "message": _ABSENT_MSG, "detail": _s(detail, 200), "items": []}


def node_top(conn: Any) -> dict:
    """[READ] CPU/memory usage per node (requires metrics-server).

    Returns ``{available: False, message, items: []}`` if metrics-server is
    absent rather than raising.
    """
    try:
        data = conn.custom.list_cluster_custom_object(
            _GROUP, _VERSION, "nodes", _request_timeout=_REQUEST_TIMEOUT
        )
    except ApiException as exc:
        if getattr(exc, "status", None) in _ABSENT_CODES:
            return _absent(getattr(exc, "reason", None))
        raise translate_api_error(exc, "metrics/nodes") from exc
    items = [
        {
            "name": _s((it.get("metadata") or {}).get("name"), 128),
            "cpu": _s((it.get("usage") or {}).get("cpu"), 32),
            "memory": _s((it.get("usage") or {}).get("memory"), 32),
        }
        for it in (data.get("items") or [])
    ]
    return {"available": True, "items": items}


def pod_top(conn: Any, namespace: str | None = None) -> dict:
    """[READ] CPU/memory usage per pod (requires metrics-server).

    Returns ``{available: False, message, items: []}`` if metrics-server is
    absent rather than raising. Omit namespace for all namespaces.
    """
    try:
        if namespace:
            data = conn.custom.list_namespaced_custom_object(
                _GROUP, _VERSION, namespace, "pods", _request_timeout=_REQUEST_TIMEOUT
            )
        else:
            data = conn.custom.list_cluster_custom_object(
                _GROUP, _VERSION, "pods", _request_timeout=_REQUEST_TIMEOUT
            )
    except ApiException as exc:
        if getattr(exc, "status", None) in _ABSENT_CODES:
            return _absent(getattr(exc, "reason", None))
        raise translate_api_error(exc, "metrics/pods") from exc
    items: list[dict] = []
    for it in data.get("items") or []:
        meta = it.get("metadata") or {}
        containers = it.get("containers") or []
        items.append(
            {
                "name": _s(meta.get("name"), 128),
                "namespace": _s(meta.get("namespace"), 64),
                "containers": [
                    {
                        "name": _s(c.get("name"), 64),
                        "cpu": _s((c.get("usage") or {}).get("cpu"), 32),
                        "memory": _s((c.get("usage") or {}).get("memory"), 32),
                    }
                    for c in containers
                ],
            }
        )
    return {"available": True, "items": items}
