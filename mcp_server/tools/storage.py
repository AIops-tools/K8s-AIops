"""MCP tools for storage resources: PVCs, PVs, StorageClasses (all read-only)."""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import storage as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pvc_list(namespace: Optional[str] = None, target: Optional[str] = None) -> list:
    """[READ] List persistent volume claims (name, status, capacity, class, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_pvcs(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pvc_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single PVC by name.

    Args:
        name: PVC name (see pvc_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_pvc(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pv_list(target: Optional[str] = None) -> list:
    """[READ] List persistent volumes (name, capacity, status, claim, class, age).

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.list_pvs(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def storageclass_list(target: Optional[str] = None) -> list:
    """[READ] List storage classes (name, provisioner, reclaim policy, default).

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.list_storageclasses(_get_connection(target))
