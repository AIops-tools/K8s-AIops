"""MCP tools for resource usage via metrics.k8s.io: ``pod_top`` / ``node_top``.

Both gracefully return ``{available: False, message, items: []}`` when
metrics-server is not installed instead of erroring.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import metrics as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def node_top(target: Optional[str] = None) -> dict:
    """[READ] CPU/memory usage per node (requires metrics-server).

    Returns ``available: False`` with a clear message when metrics-server is
    not installed.

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.node_top(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pod_top(namespace: Optional[str] = None, target: Optional[str] = None) -> dict:
    """[READ] CPU/memory usage per pod (requires metrics-server).

    Returns ``available: False`` with a clear message when metrics-server is
    not installed.

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.pod_top(_get_connection(target), namespace)
