"""Write MCP tools: scale, rollout restart, delete pod/deployment.

Every tool is wrapped with ``@governed_tool`` (the k8s-aiops harness): policy
pre-check, budget/runaway guard, graduated-autonomy risk-tier gate, audit
logging to ~/.k8s-aiops/audit.db, and undo-token recording. Tools with a clean
inverse pass an ``undo=`` lambda so the harness records a reversal descriptor
(scale_deployment → scale back to previous_replicas). delete_* and
rollout_restart have no safe inverse and record none.
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
    if isinstance(result, dict) and "previous_replicas" in result
    else None,
)
@tool_errors("dict")
def scale_deployment(
    name: str,
    replicas: int,
    namespace: Optional[str] = None,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Scale a deployment to ``replicas``. Inverse: restore previous count.

    Returns ``previous_replicas`` so the change can be undone.

    Args:
        name: Deployment name.
        replicas: Desired replica count.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.scale_deployment(_get_connection(target), name, replicas, namespace)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def rollout_restart_deployment(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Trigger a rolling restart of a deployment. No clean undo.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.rollout_restart_deployment(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def delete_pod(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Delete a pod. No undo — a controller usually recreates it.

    Args:
        name: Pod name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.delete_pod(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def delete_deployment(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Delete a deployment and its pods. HIGH RISK — no undo.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.delete_deployment(_get_connection(target), name, namespace)
