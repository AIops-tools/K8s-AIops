"""Read-only cluster-level operations: a friendly health summary + API groups.

``cluster_info`` is the fastest "is this cluster healthy?" overview;
``api_resources`` lists the available API groups/versions. All API-returned
text is run through ``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str
from k8s_aiops.ops._shared import call


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _node_ready(node: Any) -> bool:
    for cond in (node.status.conditions or []) if node.status else []:
        if cond.type == "Ready":
            return cond.status == "True"
    return False


def cluster_info(conn: Any) -> dict:
    """[READ] Friendly cluster health summary: server version, node/ns counts."""
    ver = call(conn.version.get_code, path="version")
    nodes = call(conn.core.list_node, path="nodes")
    namespaces = call(conn.core.list_namespace, path="namespaces")
    node_items = nodes.items or []
    ready_nodes = sum(1 for n in node_items if _node_ready(n))
    return {
        "server_version": _s(getattr(ver, "git_version", None), 64),
        "platform": _s(getattr(ver, "platform", None), 64),
        "node_count": len(node_items),
        "ready_nodes": ready_nodes,
        "namespace_count": len(namespaces.items or []),
    }


def api_resources(conn: Any) -> list[dict]:
    """[READ] List available API groups and their versions."""
    groups = call(conn.apis.get_api_versions, path="apis")
    out: list[dict] = []
    for group in groups.groups or []:
        out.append(
            {
                "group": _s(group.name, 128),
                "versions": [_s(v.version, 32) for v in (group.versions or [])],
                "preferred": _s(
                    group.preferred_version.version if group.preferred_version else "", 32
                ),
            }
        )
    return out
