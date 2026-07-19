"""Read-only node operations.

All API-returned text is run through ``sanitize()``; returns are high-signal
summaries (name, status, roles, version, schedulable).
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str, sanitize
from k8s_aiops.ops._shared import age_of, call

_ROLE_PREFIX = "node-role.kubernetes.io/"


def _node_roles(labels: dict | None) -> str:
    roles = [
        k[len(_ROLE_PREFIX):] or "master"
        for k in (labels or {})
        if k.startswith(_ROLE_PREFIX)
    ]
    return ",".join(sorted(roles)) or "<none>"


def _ready_status(node: Any) -> str:
    for cond in node.status.conditions or []:
        if cond.type == "Ready":
            return "Ready" if cond.status == "True" else "NotReady"
    return "Unknown"


def list_nodes(conn: Any) -> list[dict]:
    """[READ] List cluster nodes (name, status, roles, version, schedulable)."""
    result = call(conn.core.list_node, path="nodes")
    out: list[dict] = []
    for node in result.items or []:
        info = node.status.node_info
        out.append(
            {
                "name": opt_str(node.metadata.name, 128),
                "status": _ready_status(node),
                "roles": sanitize(_node_roles(node.metadata.labels), 128),
                "version": opt_str(info.kubelet_version if info else None, 64),
                "schedulable": not bool(node.spec.unschedulable),
                "age": age_of(node.metadata.creation_timestamp),
            }
        )
    return out
