"""MCP tools for deployment rollouts.

Reads: ``rollout_status``, ``rollout_history`` (low). Writes:
``rollout_undo`` (high; no clean inverse), ``rollout_pause`` ↔ ``rollout_resume``
(medium, mutual inverses), and ``set_deployment_image`` (medium; inverse restores
the captured previous image).
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import rollout as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def rollout_status(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Rollout status: desired/updated/available/unavailable + paused.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.rollout_status(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def rollout_history(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List a deployment's rollout revisions (from its replicasets).

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.rollout_history(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def rollout_undo_deployment(
    name: str,
    namespace: Optional[str] = None,
    to_revision: int = 0,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Roll a deployment back to a prior revision. HIGH RISK.

    Defaults to the immediately previous revision. No clean automatic inverse —
    re-deploy the intended image/revision to move forward again.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        to_revision: Specific revision to roll back to (0 = previous).
        target: k8s target name from config.
    """
    return ops.rollout_undo(_get_connection(target), name, namespace, to_revision)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "rollout_resume",
        "params": {"name": params.get("name"), "namespace": params.get("namespace")},
        "skill": "k8s-aiops",
        "note": "Inverse of rollout_pause: resume the deployment's rollout.",
    },
)
@tool_errors("dict")
def rollout_pause(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Pause a deployment's rollout. Inverse: rollout_resume.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.rollout_pause(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "rollout_pause",
        "params": {"name": params.get("name"), "namespace": params.get("namespace")},
        "skill": "k8s-aiops",
        "note": "Inverse of rollout_resume: pause the deployment's rollout again.",
    },
)
@tool_errors("dict")
def rollout_resume(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[WRITE] Resume a paused deployment's rollout. Inverse: rollout_pause.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.rollout_resume(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "set_deployment_image",
        "params": {
            "name": params.get("name"),
            "namespace": params.get("namespace"),
            "container": params.get("container"),
            "image": result.get("previous_image"),
        },
        "skill": "k8s-aiops",
        "note": "Inverse of set_deployment_image: restore the previous image.",
    }
    if isinstance(result, dict) and result.get("previous_image")
    else None,
)
@tool_errors("dict")
def set_deployment_image(
    name: str,
    container: str,
    image: str,
    namespace: Optional[str] = None,
    target: Optional[str] = None,
) -> dict:
    """[WRITE] Update a deployment container's image. Inverse: restore previous.

    Returns ``previous_image`` so the change can be undone.

    Args:
        name: Deployment name.
        container: Container name within the pod template (see deployment_get).
        image: New image reference (e.g. "nginx:1.27").
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.set_deployment_image(
        _get_connection(target), name, container, image, namespace
    )
