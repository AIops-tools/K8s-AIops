"""Read operations for networking resources: Ingresses and Endpoints.

All read-only; returns high-signal summaries. All API-returned text is run
through ``sanitize()``.
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


def _ingress_hosts(ing: Any) -> list[str]:
    return [_s(r.host, 200) for r in (ing.spec.rules or []) if getattr(r, "host", None)]


def _ingress_summary(ing: Any) -> dict:
    meta = ing.metadata
    spec = ing.spec
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "class": _s(spec.ingress_class_name, 64),
        "hosts": _ingress_hosts(ing),
        "age": age_of(meta.creation_timestamp),
    }


def list_ingresses(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List ingresses (name, namespace, class, hosts, age)."""
    if namespace:
        result = call(conn.networking.list_namespaced_ingress, namespace, path="ingresses")
    else:
        result = call(conn.networking.list_ingress_for_all_namespaces, path="ingresses")
    return [_ingress_summary(i) for i in (result.items or [])]


def get_ingress(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single ingress, including path→backend rules."""
    ns = namespace or conn.default_namespace()
    ing = call(conn.networking.read_namespaced_ingress, name, ns, path=f"ingresses/{name}")
    summary = _ingress_summary(ing)
    paths: list[dict] = []
    for rule in ing.spec.rules or []:
        http = getattr(rule, "http", None)
        for p in (http.paths if http else []) or []:
            svc = p.backend.service if p.backend else None
            paths.append(
                {
                    "host": _s(rule.host, 200),
                    "path": _s(p.path, 200),
                    "service": _s(svc.name if svc else None, 128),
                    "port": _s(svc.port.number if svc and svc.port else None, 16),
                }
            )
    summary["paths"] = paths
    return summary


def list_endpoints(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List endpoints (name, namespace, ready addresses, ports, age)."""
    if namespace:
        result = call(conn.core.list_namespaced_endpoints, namespace, path="endpoints")
    else:
        result = call(conn.core.list_endpoints_for_all_namespaces, path="endpoints")
    out: list[dict] = []
    for ep in result.items or []:
        addresses: list[str] = []
        ports: list[str] = []
        for subset in ep.subsets or []:
            addresses.extend(_s(a.ip, 64) for a in (subset.addresses or []))
            ports.extend(f"{p.port}/{p.protocol}" for p in (subset.ports or []))
        out.append(
            {
                "name": _s(ep.metadata.name),
                "namespace": _s(ep.metadata.namespace, 64),
                "addresses": addresses,
                "ports": [_s(p, 32) for p in ports],
                "age": age_of(ep.metadata.creation_timestamp),
            }
        )
    return out
