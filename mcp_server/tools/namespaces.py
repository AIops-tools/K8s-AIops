"""Namespace MCP tools: list (read), create (medium) / delete (high) writes.

Both writes take ``dry_run: bool = False`` — a dry run returns a
``{"dryRun": True, "wouldX": ...}`` preview without touching the cluster, and
create_namespace's undo lambda is guarded so a preview records no undo.

``delete_namespace`` additionally runs ``ops.guard_delete_namespace`` *before*
its dry-run return, so the protected-namespace and self-lockout refusals reach
the preview as well as the real call.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import namespaces as ops
from mcp_server._shared import _get_connection, _get_target_config, mcp, tool_errors


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
    name: str,
    dry_run: bool = False,
    confirm: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=high] Delete a namespace and EVERYTHING in it. HIGH RISK — no undo.

    Pass dry_run=True to preview without deleting.

    Two namespaces are refused. The cluster's control-plane namespaces
    (kube-system, kube-public, kube-node-lease) need confirm=True — deleting one
    takes DNS and pod networking with it. The namespace holding this target's own
    ServiceAccount credential is refused outright and confirm does NOT override
    it: that delete revokes the credential it is running on. Both refusals are
    raised on the dry_run path too, so a preview never shows a green wouldDelete
    for a delete that would be rejected.

    Args:
        name: Namespace name to delete.
        dry_run: If True, preview without deleting.
        confirm: Acknowledge deleting a protected control-plane namespace.
        target: k8s target name from config.
    """
    # Ahead of the dry_run return by design: preview and real call run the one
    # guard, so they can never disagree about whether this delete is allowed.
    ops.guard_delete_namespace(name, confirm=confirm, target=_get_target_config(target))
    if dry_run:
        return {"dryRun": True, "wouldDelete": {"name": name}}
    return ops.delete_namespace(_get_connection(target), name, confirm=confirm)
