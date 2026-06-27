"""MCP tool: ``pod_describe`` (read-only diagnostics).

``node_describe`` is registered alongside the other node tools in
``mcp_server/tools/nodes.py``.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import describe as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pod_describe(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Describe a pod: status, conditions, container states, recent events.

    The fastest single call to diagnose why a pod is not Ready (CrashLoopBackOff,
    ImagePullBackOff, scheduling failures).

    Args:
        name: Pod name (see pod_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.pod_describe(_get_connection(target), name, namespace)
