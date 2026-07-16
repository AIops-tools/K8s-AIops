"""Namespace MCP tools: list (read), create (medium) / delete (high) writes.

Both writes take ``dry_run: bool = False`` — a dry run returns a
``{"dryRun": True, "wouldX": ...}`` preview without touching the cluster, and
create_namespace's undo lambda is guarded so a preview records no undo.
"""

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
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def create_namespace(
    name: str, dry_run: bool = False, target: Optional[str] = None
) -> dict:
    """[WRITE][risk=medium] Create a namespace. Inverse: delete_namespace.

    Pass dry_run=True to preview without creating.

    Args:
        name: Namespace name to create.
        dry_run: If True, preview without creating.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldCreate": {"name": name}}
    return ops.create_namespace(_get_connection(target), name)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def delete_namespace(
    name: str, dry_run: bool = False, target: Optional[str] = None
) -> dict:
    """[WRITE][risk=high] Delete a namespace and EVERYTHING in it. HIGH RISK — no undo.

    Pass dry_run=True to preview without deleting.

    Args:
        name: Namespace name to delete.
        dry_run: If True, preview without deleting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldDelete": {"name": name}}
    return ops.delete_namespace(_get_connection(target), name)
