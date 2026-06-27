"""MCP tools for networking resources: ingresses and endpoints (read-only)."""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import networking as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def ingress_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List ingresses (name, namespace, class, hosts, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_ingresses(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def ingress_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single ingress, including path→backend rules.

    Args:
        name: Ingress name (see ingress_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_ingress(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def endpoints_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List endpoints (name, namespace, ready addresses, ports, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_endpoints(_get_connection(target), namespace)
