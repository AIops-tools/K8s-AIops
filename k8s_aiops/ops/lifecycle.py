"""Write operations: scale, rollout restart, delete pod/deployment, cordon.

All API-returned text is run through ``sanitize()``. Scaling reads the current
replica count first so the caller (and the undo store) can record the previous
value as the inverse. Cordon/uncordon are exact inverses of each other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from k8s_aiops.governance import sanitize
from k8s_aiops.ops._shared import call


def scale_deployment(
    conn: Any, name: str, replicas: int, namespace: str | None = None
) -> dict:
    """[WRITE] Scale a deployment to ``replicas``. Inverse: scale to previous.

    Reads the current replica count first and returns it as ``previous_replicas``
    so the change can be undone.
    """
    ns = namespace or conn.default_namespace()
    current = call(
        conn.apps.read_namespaced_deployment_scale,
        name,
        ns,
        path=f"deployments/{name}/scale",
    )
    previous = current.spec.replicas or 0
    body = {"spec": {"replicas": int(replicas)}}
    call(
        conn.apps.patch_namespaced_deployment_scale,
        name,
        ns,
        body,
        path=f"deployments/{name}/scale",
    )
    return {
        "name": sanitize(name, 128),
        "namespace": sanitize(ns, 64),
        "replicas": int(replicas),
        "previous_replicas": int(previous),
        "action": "scaled",
    }


def rollout_restart_deployment(
    conn: Any, name: str, namespace: str | None = None
) -> dict:
    """[WRITE] Trigger a rolling restart of a deployment. No clean undo.

    Patches the pod template's ``restartedAt`` annotation, which is how
    ``kubectl rollout restart`` works. There is no inverse (the old pods are
    already being replaced).
    """
    ns = namespace or conn.default_namespace()
    now = datetime.now(UTC).isoformat()
    body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": now,
                    }
                }
            }
        }
    }
    call(
        conn.apps.patch_namespaced_deployment,
        name,
        ns,
        body,
        path=f"deployments/{name}",
    )
    return {
        "name": sanitize(name, 128),
        "namespace": sanitize(ns, 64),
        "restarted_at": now,
        "action": "rollout_restarted",
    }


def delete_pod(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[WRITE] Delete a pod. No undo (a controller usually recreates it)."""
    ns = namespace or conn.default_namespace()
    call(conn.core.delete_namespaced_pod, name, ns, path=f"pods/{name}")
    return {
        "name": sanitize(name, 128),
        "namespace": sanitize(ns, 64),
        "action": "deleted",
    }


def delete_deployment(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[WRITE] Delete a deployment and its pods. HIGH RISK — no undo."""
    ns = namespace or conn.default_namespace()
    call(
        conn.apps.delete_namespaced_deployment, name, ns, path=f"deployments/{name}"
    )
    return {
        "name": sanitize(name, 128),
        "namespace": sanitize(ns, 64),
        "action": "deleted",
    }


def _set_node_unschedulable(conn: Any, name: str, unschedulable: bool) -> dict:
    body = {"spec": {"unschedulable": unschedulable}}
    call(conn.core.patch_node, name, body, path=f"nodes/{name}")
    return {
        "name": sanitize(name, 128),
        "unschedulable": unschedulable,
        "action": "cordoned" if unschedulable else "uncordoned",
    }


def cordon_node(conn: Any, name: str) -> dict:
    """[WRITE] Mark a node unschedulable (no new pods land). Inverse: uncordon."""
    return _set_node_unschedulable(conn, name, True)


def uncordon_node(conn: Any, name: str) -> dict:
    """[WRITE] Mark a node schedulable again. Inverse: cordon_node."""
    return _set_node_unschedulable(conn, name, False)
