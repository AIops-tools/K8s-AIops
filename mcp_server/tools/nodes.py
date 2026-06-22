"""Node MCP tools: list (read), cordon/uncordon (write, mutual inverses).

cordon_node and uncordon_node pass ``undo=`` lambdas pointing at each other so
the harness records the exact inverse to the undo store.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import lifecycle as life_ops
from k8s_aiops.ops import nodes as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def node_list(target: Optional[str] = None) -> list:
    """[READ] List cluster nodes (name, status, roles, version, schedulable, age).

    Args:
        target: k8s target name from config; omit to use the default.
    """
    return ops.list_nodes(_get_connection(target))


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "uncordon_node",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": "Inverse of cordon_node: make the node schedulable again.",
    },
)
@tool_errors("dict")
def cordon_node(name: str, target: Optional[str] = None) -> dict:
    """[WRITE] Mark a node unschedulable (no new pods land). Inverse: uncordon_node.

    Args:
        name: Node name (see node_list).
        target: k8s target name from config.
    """
    return life_ops.cordon_node(_get_connection(target), name)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "cordon_node",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": "Inverse of uncordon_node: mark the node unschedulable again.",
    },
)
@tool_errors("dict")
def uncordon_node(name: str, target: Optional[str] = None) -> dict:
    """[WRITE] Mark a node schedulable again. Inverse: cordon_node.

    Args:
        name: Node name (see node_list).
        target: k8s target name from config.
    """
    return life_ops.uncordon_node(_get_connection(target), name)
