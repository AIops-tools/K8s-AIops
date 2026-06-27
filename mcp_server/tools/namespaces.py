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


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "delete_namespace",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": "Inverse of create_namespace: delete the namespace just created.",
    },
)
@tool_errors("dict")
def create_namespace(name: str, target: Optional[str] = None) -> dict:
    """[WRITE] Create a namespace. Inverse: delete_namespace.

    Args:
        name: Namespace name to create.
        target: k8s target name from config.
    """
    return ops.create_namespace(_get_connection(target), name)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def delete_namespace(name: str, target: Optional[str] = None) -> dict:
    """[WRITE] Delete a namespace and EVERYTHING in it. HIGH RISK — no undo.

    Args:
        name: Namespace name to delete.
        target: k8s target name from config.
    """
    return ops.delete_namespace(_get_connection(target), name)
