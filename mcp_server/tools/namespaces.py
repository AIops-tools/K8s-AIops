"""Namespace MCP tools (read-only)."""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import namespaces as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def namespace_list(target: Optional[str] = None) -> list:
    """[READ] List namespaces (name, phase, age).

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.list_namespaces(_get_connection(target))
