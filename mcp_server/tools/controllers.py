"""MCP tools for other workload controllers: statefulsets, daemonsets, replicasets.

Reads are ``risk_level=low``. ``scale_statefulset`` is a ``medium`` write that
passes an ``undo=`` lambda restoring the previous replica count. It takes
``dry_run: bool = False`` — a dry run returns a ``{"dryRun": True, ...}``
preview without touching the cluster and never records an undo descriptor.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import controllers as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def statefulset_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List statefulsets (name, namespace, desired/ready/current, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_statefulsets(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def statefulset_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single statefulset by name.

    Args:
        name: StatefulSet name (see statefulset_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_statefulset(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def daemonset_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List daemonsets (name, namespace, desired/ready/available, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_daemonsets(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def daemonset_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single daemonset by name.

    Args:
        name: DaemonSet name (see daemonset_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_daemonset(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def replicaset_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List replicasets (name, namespace, desired/ready, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_replicasets(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "scale_statefulset",
        "params": {
            "name": params.get("name"),
            "namespace": params.get("namespace"),
            "replicas": result.get("previous_replicas"),
        },
        "skill": "k8s-aiops",
        "note": "Inverse of scale_statefulset: restore the previous replica count.",
    }
    if isinstance(result, dict)
    and not result.get("dryRun")
    and "previous_replicas" in result
    else None,
)
@tool_errors("dict")
def scale_statefulset(
    name: str,
    replicas: int,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Scale a statefulset to ``replicas``. Inverse: restore previous count.

    Pass dry_run=True to preview without scaling (no undo is recorded for a preview).

    Args:
        name: StatefulSet name.
        replicas: Desired replica count.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without scaling.
        target: k8s target name from config.
    """
    if dry_run:
        return {
            "dryRun": True,
            "wouldScale": {"name": name, "namespace": namespace, "replicas": replicas},
        }
    return ops.scale_statefulset(_get_connection(target), name, replicas, namespace)
