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

from mcp.server.fastmcp import FastMCP

from k8s_aiops.config import load_config
from k8s_aiops.connection import ConnectionManager, K8sApiError
from k8s_aiops.governance import sanitize

logger = logging.getLogger(__name__)

_DOCTOR_HINT = "Run 'k8s-aiops doctor' to verify the kubeconfig context and cluster access."


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
        return sanitize(str(exc), 300)
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
                return {"error": msg, "hint": _DOCTOR_HINT}

        return wrapper

    return decorator


mcp = FastMCP(
    "k8s-aiops",
    instructions=(
        "Governed Kubernetes operations (preview). Works with any cluster a "
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


def _get_connection(target: Optional[str] = None) -> Any:
    """Return a Kubernetes connection, lazily initialising the manager."""
    global _conn_mgr  # noqa: PLW0603
    if _conn_mgr is None:
        config_path_str = os.environ.get("K8S_AIOPS_CONFIG")
        config_path = Path(config_path_str) if config_path_str else None
        _conn_mgr = ConnectionManager(load_config(config_path))
    return _conn_mgr.connect(target)
