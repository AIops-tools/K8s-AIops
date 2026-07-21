"""Write MCP tools: scale, rollout restart, delete pod/deployment.

Every tool is wrapped with ``@governed_tool`` (the k8s-aiops harness): audit
logging to ~/.k8s-aiops/audit.db, a token/runaway budget guard, a descriptive
risk-tier label on each audit row, and undo-token recording. Tools with a clean
inverse pass an ``undo=`` lambda so the harness records a reversal descriptor
(scale_deployment → scale back to previous_replicas). delete_* and
rollout_restart have no safe inverse and record none.

Every write takes ``dry_run: bool = False`` — a dry run returns a
``{"dryRun": True, "wouldX": ...}`` preview without touching the cluster, and
the undo lambdas are guarded so a preview never records an undo descriptor.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import lifecycle as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "scale_deployment",
        "params": {
            "name": params.get("name"),
            "namespace": params.get("namespace"),
            "replicas": result.get("previous_replicas"),
        },
        "skill": "k8s-aiops",
        "note": "Inverse of scale_deployment: restore the previous replica count.",
    }
    if isinstance(result, dict)
    and not result.get("dryRun")
    and "previous_replicas" in result
    else None,
)
@tool_errors("dict")
def scale_deployment(
    name: str,
    replicas: int,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Scale a deployment to ``replicas``. Inverse: restore previous count.

    Returns ``previous_replicas`` so the change can be undone. Pass dry_run=True
    to preview without changing anything (no undo is recorded for a preview).

    Args:
        name: Deployment name.
        replicas: Desired replica count.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without scaling.
        target: k8s target name from config.
    """
    if dry_run:
        return {
            "dryRun": True,
            "wouldScale": {"name": name, "namespace": namespace, "replicas": replicas},
        }
    return ops.scale_deployment(_get_connection(target), name, replicas, namespace)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def rollout_restart_deployment(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Trigger a rolling restart of a deployment. No clean undo.

    Pass dry_run=True to preview without restarting.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without restarting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldRestart": {"name": name, "namespace": namespace}}
    return ops.rollout_restart_deployment(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def delete_pod(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Delete a pod. No undo — a controller usually recreates it.

    Pass dry_run=True to preview without deleting.

    Args:
        name: Pod name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without deleting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldDelete": {"name": name, "namespace": namespace}}
    return ops.delete_pod(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def delete_deployment(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=high] Delete a deployment and its pods. HIGH RISK — no undo.

    Pass dry_run=True to preview without deleting.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without deleting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldDelete": {"name": name, "namespace": namespace}}
    return ops.delete_deployment(_get_connection(target), name, namespace)
