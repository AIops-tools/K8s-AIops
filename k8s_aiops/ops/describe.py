"""Read-only ``describe`` operations for pods and nodes.

These mirror ``kubectl describe``: status, conditions, container statuses with
restart counts, taints/capacity, and recent events for the object. All
API-returned text is run through ``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import sanitize
from k8s_aiops.ops._shared import age_of, call


def _s(value: Any, limit: int = 128) -> str:
    return sanitize(str(value if value is not None else ""), limit)


def _conditions(conditions: Any) -> list[dict]:
    return [
        {"type": _s(c.type, 64), "status": _s(c.status, 16), "reason": _s(c.reason, 128)}
        for c in (conditions or [])
    ]


def _container_state(cs: Any) -> str:
    state = cs.state
    if not state:
        return "unknown"
    if getattr(state, "running", None):
        return "running"
    if getattr(state, "waiting", None):
        return _s(f"waiting:{state.waiting.reason}", 64)
    if getattr(state, "terminated", None):
        return _s(f"terminated:{state.terminated.reason}", 64)
    return "unknown"


def _pod_events(conn: Any, name: str, ns: str) -> list[dict]:
    result = call(
        conn.core.list_namespaced_event,
        ns,
        field_selector=f"involvedObject.name={name}",
        path="events",
    )
    out: list[dict] = []
    for ev in result.items or []:
        out.append(
            {
                "type": _s(ev.type, 32),
                "reason": _s(ev.reason, 64),
                "message": _s(ev.message, 200),
                "age": age_of(ev.last_timestamp or ev.metadata.creation_timestamp),
            }
        )
    return out


def pod_describe(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Describe a pod: status, conditions, container states, recent events."""
    ns = namespace or conn.default_namespace()
    pod = call(conn.core.read_namespaced_pod, name, ns, path=f"pods/{name}")
    status = pod.status
    containers = [
        {
            "name": _s(cs.name, 64),
            "ready": bool(cs.ready),
            "restarts": cs.restart_count,
            "state": _container_state(cs),
            "image": _s(cs.image, 200),
        }
        for cs in (status.container_statuses or [])
    ]
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "phase": _s(status.phase, 32),
        "node": _s(pod.spec.node_name, 128),
        "pod_ip": _s(status.pod_ip, 64),
        "conditions": _conditions(status.conditions),
        "containers": containers,
        "events": _pod_events(conn, name, ns),
    }


def _taints(spec: Any) -> list[dict]:
    return [
        {"key": _s(t.key, 128), "value": _s(t.value, 128), "effect": _s(t.effect, 32)}
        for t in (getattr(spec, "taints", None) or [])
    ]


def node_describe(conn: Any, name: str) -> dict:
    """[READ] Describe a node: capacity, allocatable, conditions, taints."""
    node = call(conn.core.read_node, name, path=f"nodes/{name}")
    status = node.status
    capacity = {_s(k, 64): _s(v, 64) for k, v in (status.capacity or {}).items()}
    allocatable = {_s(k, 64): _s(v, 64) for k, v in (status.allocatable or {}).items()}
    return {
        "name": _s(name),
        "schedulable": not bool(node.spec.unschedulable),
        "capacity": capacity,
        "allocatable": allocatable,
        "conditions": _conditions(status.conditions),
        "taints": _taints(node.spec),
        "age": age_of(node.metadata.creation_timestamp),
    }
