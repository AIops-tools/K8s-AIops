"""Rollout operations for deployments: status/history (read) and the
write operations undo / pause / resume / set-image.

Write operations read the BEFORE state first so the undo store records an
accurate inverse: ``set_deployment_image`` returns the previous image,
``rollout_pause`` ↔ ``rollout_resume`` are mutual inverses, and ``rollout_undo``
returns the revision it rolled away from. All API text is ``sanitize()``d.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import sanitize
from k8s_aiops.ops._shared import call

_REVISION_ANNO = "deployment.kubernetes.io/revision"
_HASH_LABEL = "pod-template-hash"


def _s(value: Any, limit: int = 128) -> str:
    return sanitize(str(value if value is not None else ""), limit)


def rollout_status(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Rollout status: desired/updated/available/unavailable + paused."""
    ns = namespace or conn.default_namespace()
    dep = call(conn.apps.read_namespaced_deployment, name, ns, path=f"deployments/{name}")
    status = dep.status
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "desired": dep.spec.replicas,
        "updated": (status.updated_replicas or 0) if status else 0,
        "ready": (status.ready_replicas or 0) if status else 0,
        "available": (status.available_replicas or 0) if status else 0,
        "unavailable": (status.unavailable_replicas or 0) if status else 0,
        "paused": bool(dep.spec.paused),
    }


def _owned_replicasets(conn: Any, name: str, ns: str) -> list[Any]:
    result = call(conn.apps.list_namespaced_replica_set, ns, path="replicasets")
    owned = []
    for rs in result.items or []:
        owners = rs.metadata.owner_references or []
        if any(o.name == name and o.kind == "Deployment" for o in owners):
            owned.append(rs)
    return owned


def _revision_of(rs: Any) -> int:
    try:
        return int((rs.metadata.annotations or {}).get(_REVISION_ANNO, "0"))
    except (ValueError, TypeError):
        return 0


def rollout_history(conn: Any, name: str, namespace: str | None = None) -> list[dict]:
    """[READ] List a deployment's rollout revisions (from its replicasets)."""
    ns = namespace or conn.default_namespace()
    revisions = []
    for rs in _owned_replicasets(conn, name, ns):
        containers = rs.spec.template.spec.containers or []
        revisions.append(
            {
                "revision": _revision_of(rs),
                "replicaset": _s(rs.metadata.name, 128),
                "images": [_s(c.image, 200) for c in containers],
            }
        )
    return sorted(revisions, key=lambda r: r["revision"])


def _current_revision(dep: Any) -> int:
    try:
        return int((dep.metadata.annotations or {}).get(_REVISION_ANNO, "0"))
    except (ValueError, TypeError):
        return 0


def rollout_undo(
    conn: Any, name: str, namespace: str | None = None, to_revision: int = 0
) -> dict:
    """[WRITE] Roll a deployment back to a prior revision. HIGH RISK.

    Defaults to the immediately previous revision. Returns ``from_revision`` so
    the change can be reversed by undoing back to it.
    """
    ns = namespace or conn.default_namespace()
    dep = call(conn.apps.read_namespaced_deployment, name, ns, path=f"deployments/{name}")
    current = _current_revision(dep)
    owned = _owned_replicasets(conn, name, ns)
    if to_revision > 0:
        target = next((rs for rs in owned if _revision_of(rs) == to_revision), None)
    else:
        prior = [rs for rs in owned if _revision_of(rs) < current]
        target = max(prior, key=_revision_of) if prior else None
    if target is None:
        raise ValueError(
            f"No prior revision found for deployment '{name}' to roll back to."
        )
    template = target.spec.template
    labels = dict((template.metadata.labels or {}) if template.metadata else {})
    labels.pop(_HASH_LABEL, None)
    body = {
        "spec": {
            "template": {
                "metadata": {"labels": labels},
                "spec": _container_spec(template),
            }
        }
    }
    call(conn.apps.patch_namespaced_deployment, name, ns, body, path=f"deployments/{name}")
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "rolled_to_revision": _revision_of(target),
        "from_revision": current,
        "action": "rolled_back",
    }


def _container_spec(template: Any) -> dict:
    containers = template.spec.containers or []
    return {"containers": [{"name": c.name, "image": c.image} for c in containers]}


def _set_paused(conn: Any, name: str, ns: str, paused: bool) -> dict:
    body = {"spec": {"paused": paused}}
    call(conn.apps.patch_namespaced_deployment, name, ns, body, path=f"deployments/{name}")
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "paused": paused,
        "action": "paused" if paused else "resumed",
    }


def rollout_pause(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[WRITE] Pause a deployment's rollout. Inverse: rollout_resume."""
    return _set_paused(conn, name, namespace or conn.default_namespace(), True)


def rollout_resume(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[WRITE] Resume a paused deployment's rollout. Inverse: rollout_pause."""
    return _set_paused(conn, name, namespace or conn.default_namespace(), False)


def set_deployment_image(
    conn: Any,
    name: str,
    container: str,
    image: str,
    namespace: str | None = None,
) -> dict:
    """[WRITE] Update a deployment container's image. Inverse: restore previous.

    Reads the deployment first to capture the BEFORE image, returned as
    ``previous_image`` so the change can be undone accurately.
    """
    ns = namespace or conn.default_namespace()
    dep = call(conn.apps.read_namespaced_deployment, name, ns, path=f"deployments/{name}")
    containers = dep.spec.template.spec.containers or []
    match = next((c for c in containers if c.name == container), None)
    if match is None:
        available = ", ".join(c.name for c in containers) or "(none)"
        raise ValueError(
            f"Container '{container}' not found in deployment '{name}'. "
            f"Available: {available}"
        )
    previous_image = match.image
    body = {
        "spec": {
            "template": {
                "spec": {"containers": [{"name": container, "image": image}]}
            }
        }
    }
    call(conn.apps.patch_namespaced_deployment, name, ns, body, path=f"deployments/{name}")
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "container": _s(container, 64),
        "image": _s(image, 200),
        "previous_image": _s(previous_image, 200),
        "action": "image_set",
    }
