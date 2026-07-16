"""MCP tools for deployment rollouts.

Reads: ``rollout_status``, ``rollout_history`` (low). Writes:
``rollout_undo`` (high; no clean inverse), ``rollout_pause`` ↔ ``rollout_resume``
(medium, mutual inverses), and ``set_deployment_image`` (medium; inverse restores
the captured previous image).

Every write takes ``dry_run: bool = False`` — a dry run returns a
``{"dryRun": True, "wouldX": ...}`` preview without touching the cluster, and
the undo lambdas are guarded so a preview never records an undo descriptor.
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
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=high] Roll a deployment back to a prior revision. HIGH RISK.

    Defaults to the immediately previous revision. No clean automatic inverse —
    re-deploy the intended image/revision to move forward again. Pass
    dry_run=True to preview without rolling back.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        to_revision: Specific revision to roll back to (0 = previous).
        dry_run: If True, preview without rolling back.
        target: k8s target name from config.
    """
    if dry_run:
        return {
            "dryRun": True,
            "wouldRollBack": {
                "name": name,
                "namespace": namespace,
                "to_revision": to_revision or "previous",
            },
        }
    return ops.rollout_undo(_get_connection(target), name, namespace, to_revision)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "rollout_resume",
        "params": {"name": params.get("name"), "namespace": params.get("namespace")},
        "skill": "k8s-aiops",
        "note": "Inverse of rollout_pause: resume the deployment's rollout.",
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def rollout_pause(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Pause a deployment's rollout. Inverse: rollout_resume.

    Pass dry_run=True to preview without pausing.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without pausing.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldPause": {"name": name, "namespace": namespace}}
    return ops.rollout_pause(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: {
        "tool": "rollout_pause",
        "params": {"name": params.get("name"), "namespace": params.get("namespace")},
        "skill": "k8s-aiops",
        "note": "Inverse of rollout_resume: pause the deployment's rollout again.",
    }
    if isinstance(result, dict) and not result.get("dryRun")
    else None,
)
@tool_errors("dict")
def rollout_resume(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Resume a paused deployment's rollout. Inverse: rollout_pause.

    Pass dry_run=True to preview without resuming.

    Args:
        name: Deployment name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without resuming.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldResume": {"name": name, "namespace": namespace}}
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
    if isinstance(result, dict)
    and not result.get("dryRun")
    and result.get("previous_image")
    else None,
)
@tool_errors("dict")
def set_deployment_image(
    name: str,
    container: str,
    image: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=medium] Update a deployment container's image. Inverse: restore previous.

    Returns ``previous_image`` so the change can be undone. Pass dry_run=True to
    preview without changing anything (no undo is recorded for a preview).

    Args:
        name: Deployment name.
        container: Container name within the pod template (see deployment_get).
        image: New image reference (e.g. "nginx:1.27").
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without updating the image.
        target: k8s target name from config.
    """
    if dry_run:
        return {
            "dryRun": True,
            "wouldSetImage": {
                "name": name,
                "namespace": namespace,
                "container": container,
                "image": image,
            },
        }
    return ops.set_deployment_image(
        _get_connection(target), name, container, image, namespace
    )
