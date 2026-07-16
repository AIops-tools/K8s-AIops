"""Node MCP tools: list (read), cordon/uncordon (write, mutual inverses).

cordon_node and uncordon_node pass ``undo=`` lambdas pointing at each other so
the harness records the exact inverse to the undo store.

Every write takes ``dry_run: bool = False`` — a dry run returns a
``{"dryRun": True, "wouldX": ...}`` preview without touching the cluster, and
the undo lambdas are guarded so a preview never records an undo descriptor.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import describe as describe_ops
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
@governed_tool(risk_level="low")
@tool_errors("dict")
def node_describe(name: str, target: Optional[str] = None) -> dict:
    """[READ] Describe a node: capacity, allocatable, conditions, taints.

    Args:
        name: Node name (see node_list).
        target: k8s target name from config.
    """
    return describe_ops.node_describe(_get_connection(target), name)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "uncordon_node",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": "Inverse of cordon_node: make the node schedulable again.",
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def cordon_node(name: str, dry_run: bool = False, target: Optional[str] = None) -> dict:
    """[WRITE][risk=medium] Mark a node unschedulable (no new pods land). Inverse: uncordon_node.

    Pass dry_run=True to preview without cordoning.

    Args:
        name: Node name (see node_list).
        dry_run: If True, preview without cordoning.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldCordon": {"name": name}}
    return life_ops.cordon_node(_get_connection(target), name)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "cordon_node",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": "Inverse of uncordon_node: mark the node unschedulable again.",
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def uncordon_node(name: str, dry_run: bool = False, target: Optional[str] = None) -> dict:
    """[WRITE][risk=medium] Mark a node schedulable again. Inverse: cordon_node.

    Pass dry_run=True to preview without uncordoning.

    Args:
        name: Node name (see node_list).
        dry_run: If True, preview without uncordoning.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldUncordon": {"name": name}}
    return life_ops.uncordon_node(_get_connection(target), name)


@mcp.tool()
@governed_tool(
    risk_level="high",
    undo=lambda params, result: {
        "tool": "uncordon_node",
        "params": {"name": params.get("name")},
        "skill": "k8s-aiops",
        "note": (
            "Partial inverse of drain_node: uncordon re-enables scheduling. "
            "Evicted pods are NOT restored — their controllers reschedule them."
        ),
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def drain_node(name: str, dry_run: bool = False, target: Optional[str] = None) -> dict:
    """[WRITE][risk=high] Cordon a node and evict its pods. HIGH RISK — no full undo.

    DaemonSet-managed and mirror pods are skipped (like ``kubectl drain``). The
    cordon is reversible (uncordon_node); the evictions are not. Pass
    dry_run=True to preview without draining.

    Args:
        name: Node name (see node_list).
        dry_run: If True, preview without cordoning or evicting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldDrain": {"name": name}}
    return life_ops.drain_node(_get_connection(target), name)
