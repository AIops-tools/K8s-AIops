"""MCP tools: ``cluster_info`` (health summary) and ``api_resources`` (read-only)."""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import cluster as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def cluster_info(target: Optional[str] = None) -> dict:
    """[READ] Friendly cluster health summary: server version, node/ns counts.

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.cluster_info(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def api_resources(target: Optional[str] = None) -> list:
    """[READ] List available API groups and their versions.

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.api_resources(_get_connection(target))
