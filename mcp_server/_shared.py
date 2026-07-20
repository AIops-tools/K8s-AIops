"""Shared MCP server primitives: the FastMCP instance, connection helper,
error sanitisation, and the ``@tool_errors`` decorator.

Tool modules under ``mcp_server/tools/`` import ``mcp`` from here and register
their ``@mcp.tool()`` functions onto it. ``mcp_server/server.py`` then imports
those modules and runs the server.

Keep ``Optional[X]`` (never PEP 604 ``X | None``) in any FastMCP-reflected
tool signature — on older mcp/pydantic the union eval'd to ``types.UnionType``
crashes FastMCP's ``issubclass`` check.
"""

import functools
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

import urllib3
from mcp.server.fastmcp import FastMCP

from k8s_aiops.config import load_config
from k8s_aiops.connection import ConnectionManager, K8sApiError
from k8s_aiops.governance import mark_unknown, sanitize

logger = logging.getLogger(__name__)

_DOCTOR_HINT = "Run 'k8s-aiops doctor' to verify the kubeconfig context and cluster access."


# Failures that leave the request's fate genuinely undetermined: the bytes went
# out and either the response or the rest of the connection was lost. A write
# that hits one of these MAY have taken effect on the API server.
#
# Deliberately narrow, and these are the client library's transport errors, not
# its API errors: K8sApiError carries a status, which means the API server
# answered and the outcome is known. MaxRetryError wraps a connection that was
# never established. Marking either 'unknown' would cry wolf on every
# unreachable cluster.
_UNDETERMINED_ERRORS = (
    urllib3.exceptions.ReadTimeoutError,
    urllib3.exceptions.ProtocolError,
)


# Long enough to carry the remediation sentence. These messages teach the
# caller what to do instead, and that clause comes last — a 300-char cap cut
# it off silently on every refusal long enough to need one.
_ERROR_MAX = 800


def _safe_error(exc: Exception, tool: str) -> str:
    """Return an agent-safe error string; log full detail server-side only."""
    logger.error("Tool %s failed", tool, exc_info=True)
    _passthrough = (
        ValueError,
        FileNotFoundError,
        KeyError,
        PermissionError,
        TimeoutError,
        ConnectionError,
        K8sApiError,
    )
    if isinstance(exc, _passthrough):
        return sanitize(str(exc), _ERROR_MAX)
    return f"{type(exc).__name__}: operation failed."


def tool_errors(shape: str = "dict") -> Callable:
    """Wrap a tool body in the canonical try/except → ``_safe_error`` pattern.

    Place this *between* ``@governed_tool`` and the function so the audit
    decorator and FastMCP still see the original signature.
    """

    def decorator(func: Callable) -> Callable:
        name = func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 — sanitised below
                msg = _safe_error(e, name)
                if shape == "list":
                    return [{"error": msg, "hint": _DOCTOR_HINT}]
                if shape == "str":
                    return f"Error: {msg} {_DOCTOR_HINT}"
                payload = {"error": msg, "hint": _DOCTOR_HINT}
                # Flatten the exception into a dict and its type is gone
                # for good — so classify here, while it is still known,
                # whether the operation may nonetheless have taken effect.
                if isinstance(e, _UNDETERMINED_ERRORS):
                    return mark_unknown(payload)
                return payload

        return wrapper

    return decorator


mcp = FastMCP(
    "k8s-aiops",
    instructions=(
        "Governed Kubernetes operations. Works with any cluster a "
        "kubeconfig can reach — standard Kubernetes, k3s, EKS, GKE, AKS. Read "
        "tools cover pods, deployments, statefulsets, daemonsets, replicasets, "
        "jobs, cronjobs, services, ingresses, endpoints, configmaps, secrets "
        "(names/keys only — values are never returned), PVCs/PVs/storageclasses, "
        "nodes, namespaces, events, pod logs, pod/node describe, rollout "
        "status/history, pod/node top (metrics-server), and a cluster_info health "
        "summary. Write tools: scale deployments/statefulsets, rollout "
        "restart/undo/pause/resume, set deployment image, delete "
        "pods/deployments/jobs, create/delete namespaces, and cordon/uncordon/drain "
        "nodes. A 'target' selects a kube context from config. Every tool runs "
        "through the k8s-aiops governance harness (audit / budget / risk-tier / "
        "undo)."
    ),
)

_conn_mgr: Optional[ConnectionManager] = None


def _manager() -> ConnectionManager:
    """Return the shared ConnectionManager, lazily initialising it."""
    global _conn_mgr  # noqa: PLW0603
    if _conn_mgr is None:
        config_path_str = os.environ.get("K8S_AIOPS_CONFIG")
        config_path = Path(config_path_str) if config_path_str else None
        _conn_mgr = ConnectionManager(load_config(config_path))
    return _conn_mgr


def _get_connection(target: Optional[str] = None) -> Any:
    """Return a Kubernetes connection, lazily initialising the manager."""
    return _manager().connect(target)


def _get_target_config(target: Optional[str] = None) -> Any:
    """Resolve a target's config without building an API client.

    Write guards call this on the dry-run path, where ``_get_connection`` is out
    of bounds: a preview may read (here, the kubeconfig on disk) but must never
    build a client it could accidentally write through.
    """
    return _manager().target_config(target)
