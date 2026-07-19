"""Read/write operations for other workload controllers.

StatefulSets, DaemonSets, ReplicaSets. Reads return high-signal summaries; the
one write here (``scale_statefulset``) reads the current replica count first so
the caller and the undo store can record the previous value as the inverse.
All API-returned text is run through ``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str
from k8s_aiops.ops._shared import age_of, call


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _statefulset_summary(sts: Any) -> dict:
    meta = sts.metadata
    status = sts.status
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "desired": sts.spec.replicas,
        "ready": (status.ready_replicas or 0) if status else 0,
        "current": (status.current_replicas or 0) if status else 0,
        "age": age_of(meta.creation_timestamp),
    }


def list_statefulsets(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List statefulsets (name, namespace, desired/ready/current, age)."""
    if namespace:
        result = call(conn.apps.list_namespaced_stateful_set, namespace, path="statefulsets")
    else:
        result = call(conn.apps.list_stateful_set_for_all_namespaces, path="statefulsets")
    return [_statefulset_summary(s) for s in (result.items or [])]


def get_statefulset(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single statefulset by name."""
    ns = namespace or conn.default_namespace()
    sts = call(
        conn.apps.read_namespaced_stateful_set, name, ns, path=f"statefulsets/{name}"
    )
    summary = _statefulset_summary(sts)
    summary["service_name"] = _s(sts.spec.service_name, 128)
    containers = sts.spec.template.spec.containers or []
    summary["images"] = [_s(c.image, 200) for c in containers]
    return summary


def _daemonset_summary(ds: Any) -> dict:
    meta = ds.metadata
    status = ds.status
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "desired": (status.desired_number_scheduled or 0) if status else 0,
        "ready": (status.number_ready or 0) if status else 0,
        "available": (status.number_available or 0) if status else 0,
        "age": age_of(meta.creation_timestamp),
    }


def list_daemonsets(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List daemonsets (name, namespace, desired/ready/available, age)."""
    if namespace:
        result = call(conn.apps.list_namespaced_daemon_set, namespace, path="daemonsets")
    else:
        result = call(conn.apps.list_daemon_set_for_all_namespaces, path="daemonsets")
    return [_daemonset_summary(d) for d in (result.items or [])]


def get_daemonset(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single daemonset by name."""
    ns = namespace or conn.default_namespace()
    ds = call(conn.apps.read_namespaced_daemon_set, name, ns, path=f"daemonsets/{name}")
    summary = _daemonset_summary(ds)
    containers = ds.spec.template.spec.containers or []
    summary["images"] = [_s(c.image, 200) for c in containers]
    return summary


def list_replicasets(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List replicasets (name, namespace, desired/ready, age)."""
    if namespace:
        result = call(conn.apps.list_namespaced_replica_set, namespace, path="replicasets")
    else:
        result = call(conn.apps.list_replica_set_for_all_namespaces, path="replicasets")
    out: list[dict] = []
    for rs in result.items or []:
        status = rs.status
        out.append(
            {
                "name": _s(rs.metadata.name),
                "namespace": _s(rs.metadata.namespace, 64),
                "desired": rs.spec.replicas,
                "ready": (status.ready_replicas or 0) if status else 0,
                "age": age_of(rs.metadata.creation_timestamp),
            }
        )
    return out


def scale_statefulset(
    conn: Any, name: str, replicas: int, namespace: str | None = None
) -> dict:
    """[WRITE] Scale a statefulset to ``replicas``. Inverse: scale to previous.

    Reads the current replica count first and returns it as ``previous_replicas``
    so the change can be undone.
    """
    ns = namespace or conn.default_namespace()
    current = call(
        conn.apps.read_namespaced_stateful_set_scale,
        name,
        ns,
        path=f"statefulsets/{name}/scale",
    )
    previous = (current.spec.replicas or 0) if current.spec else 0
    body = {"spec": {"replicas": int(replicas)}}
    call(
        conn.apps.patch_namespaced_stateful_set_scale,
        name,
        ns,
        body,
        path=f"statefulsets/{name}/scale",
    )
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "replicas": int(replicas),
        "previous_replicas": int(previous),
        "action": "scaled",
    }
