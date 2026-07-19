"""Read-only workload operations: pods, deployments, services, events, logs.

All API-returned text is run through ``sanitize()`` before reaching the caller
(output hygiene). Returns are high-signal summaries, not full blobs.
Listing is namespace-scoped when a namespace is given, otherwise all-namespaces.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str, sanitize
from k8s_aiops.ops._shared import age_of, call


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _pod_summary(pod: Any) -> dict:
    """Reduce a V1Pod to a high-signal summary."""
    meta = pod.metadata
    status = pod.status
    container_statuses = status.container_statuses or []
    ready = sum(1 for c in container_statuses if c.ready)
    total = len(container_statuses) or len(pod.spec.containers or [])
    restarts = sum(c.restart_count for c in container_statuses)
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "phase": _s(status.phase, 32),
        "ready": f"{ready}/{total}",
        "restarts": restarts,
        "node": _s(pod.spec.node_name, 128),
        "age": age_of(meta.creation_timestamp),
    }


def list_pods(
    conn: Any, namespace: str | None = None, label_selector: str | None = None
) -> list[dict]:
    """[READ] List pods (name, namespace, phase, ready, restarts, node, age).

    Omit namespace to list across all namespaces. Use get_pod for full detail.
    """
    kw: dict[str, Any] = {}
    if label_selector:
        kw["label_selector"] = label_selector
    if namespace:
        result = call(
            conn.core.list_namespaced_pod, namespace, path="pods", **kw
        )
    else:
        result = call(conn.core.list_pod_for_all_namespaces, path="pods", **kw)
    return [_pod_summary(p) for p in (result.items or [])]


def get_pod(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single pod by name."""
    ns = namespace or conn.default_namespace()
    pod = call(conn.core.read_namespaced_pod, name, ns, path=f"pods/{name}")
    summary = _pod_summary(pod)
    summary["host_ip"] = _s(pod.status.host_ip, 64)
    summary["pod_ip"] = _s(pod.status.pod_ip, 64)
    summary["containers"] = [_s(c.name, 64) for c in (pod.spec.containers or [])]
    return summary


def get_pod_logs(
    conn: Any,
    name: str,
    namespace: str | None = None,
    tail_lines: int = 100,
    container: str | None = None,
) -> dict:
    """[READ] Return the most recent log lines for a pod (default 100 lines)."""
    ns = namespace or conn.default_namespace()
    kw: dict[str, Any] = {"tail_lines": max(1, tail_lines)}
    if container:
        kw["container"] = container
    logs = call(
        conn.core.read_namespaced_pod_log, name, ns, path=f"pods/{name}/log", **kw
    )
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "tail_lines": kw["tail_lines"],
        "logs": sanitize(str(logs or ""), 8000),
    }


def _deployment_summary(dep: Any) -> dict:
    meta = dep.metadata
    status = dep.status
    spec = dep.spec
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "desired": spec.replicas,
        "ready": status.ready_replicas or 0,
        "available": status.available_replicas or 0,
        "age": age_of(meta.creation_timestamp),
    }


def list_deployments(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List deployments (name, namespace, desired/ready/available, age)."""
    if namespace:
        result = call(
            conn.apps.list_namespaced_deployment, namespace, path="deployments"
        )
    else:
        result = call(
            conn.apps.list_deployment_for_all_namespaces, path="deployments"
        )
    return [_deployment_summary(d) for d in (result.items or [])]


def get_deployment(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single deployment by name."""
    ns = namespace or conn.default_namespace()
    dep = call(
        conn.apps.read_namespaced_deployment, name, ns, path=f"deployments/{name}"
    )
    summary = _deployment_summary(dep)
    summary["strategy"] = _s(dep.spec.strategy.type if dep.spec.strategy else None, 32)
    containers = dep.spec.template.spec.containers or []
    summary["images"] = [_s(c.image, 200) for c in containers]
    return summary


def list_services(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List services (name, namespace, type, cluster IP, ports)."""
    if namespace:
        result = call(
            conn.core.list_namespaced_service, namespace, path="services"
        )
    else:
        result = call(
            conn.core.list_service_for_all_namespaces, path="services"
        )
    out: list[dict] = []
    for svc in result.items or []:
        ports = ",".join(
            f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])
        )
        out.append(
            {
                "name": _s(svc.metadata.name),
                "namespace": _s(svc.metadata.namespace, 64),
                "type": _s(svc.spec.type, 32),
                "cluster_ip": _s(svc.spec.cluster_ip, 64),
                "ports": _s(ports, 128),
            }
        )
    return out


def list_events(conn: Any, namespace: str | None = None, limit: int = 50) -> dict:
    """[READ] List recent events (type, reason, object, message, age).

    Namespace-scoped when given; otherwise across all namespaces.

    Returns an envelope rather than a bare list::

        {"events": [...], "returned": 50, "limit": 50, "truncated": true}

    so a truncated read announces itself. A bare list cannot say "there is
    more" — the consumer has to infer it from the length happening to equal the
    limit, and a smaller local model faced with a capped result tends to report
    that it saw everything. One extra event is requested so ``truncated`` is
    *measured* rather than guessed from a length coincidence.
    """
    requested = max(1, int(limit))
    if namespace:
        result = call(
            conn.core.list_namespaced_event,
            namespace,
            limit=requested + 1,
            path="events",
        )
    else:
        result = call(
            conn.core.list_event_for_all_namespaces,
            limit=requested + 1,
            path="events",
        )
    raw = list(result.items or [])
    truncated = len(raw) > requested
    out: list[dict] = []
    for ev in raw[:requested]:
        obj = ev.involved_object
        out.append(
            {
                "type": _s(ev.type, 32),
                "reason": _s(ev.reason, 64),
                "object": _s(f"{obj.kind}/{obj.name}" if obj else None, 128),
                "namespace": _s(ev.metadata.namespace, 64),
                "message": _s(ev.message, 200),
                "age": age_of(ev.last_timestamp or ev.metadata.creation_timestamp),
            }
        )
    return {
        "events": out,
        "returned": len(out),
        "limit": requested,
        "truncated": truncated,
    }
