"""Read operations for storage resources: PVCs, PVs, StorageClasses.

All read-only; returns high-signal summaries. All API-returned text is run
through ``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import sanitize
from k8s_aiops.ops._shared import age_of, call


def _s(value: Any, limit: int = 128) -> str:
    return sanitize(str(value if value is not None else ""), limit)


def _capacity(resources: Any) -> str:
    if not resources:
        return ""
    # `requests` here is a k8s resource-requests dict, not the HTTP library;
    # bandit's B113 (request-without-timeout) is a false positive.
    requests = getattr(resources, "requests", None) or {}
    return _s(requests.get("storage", ""), 32)  # nosec B113


def _pvc_summary(pvc: Any) -> dict:
    meta = pvc.metadata
    status = pvc.status
    spec = pvc.spec
    actual = (status.capacity or {}).get("storage", "") if status else ""
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "status": _s(status.phase if status else "", 32),
        "volume": _s(spec.volume_name, 128),
        "capacity": _s(actual, 32) or _capacity(spec.resources),
        "storage_class": _s(spec.storage_class_name, 64),
        "age": age_of(meta.creation_timestamp),
    }


def list_pvcs(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List persistent volume claims (name, status, capacity, class, age)."""
    if namespace:
        result = call(
            conn.core.list_namespaced_persistent_volume_claim, namespace, path="pvcs"
        )
    else:
        result = call(
            conn.core.list_persistent_volume_claim_for_all_namespaces, path="pvcs"
        )
    return [_pvc_summary(p) for p in (result.items or [])]


def get_pvc(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single PVC by name."""
    ns = namespace or conn.default_namespace()
    pvc = call(
        conn.core.read_namespaced_persistent_volume_claim, name, ns, path=f"pvcs/{name}"
    )
    summary = _pvc_summary(pvc)
    summary["access_modes"] = [_s(m, 32) for m in (pvc.spec.access_modes or [])]
    return summary


def list_pvs(conn: Any) -> list[dict]:
    """[READ] List persistent volumes (name, capacity, status, claim, class, age)."""
    result = call(conn.core.list_persistent_volume, path="pvs")
    out: list[dict] = []
    for pv in result.items or []:
        spec = pv.spec
        status = pv.status
        capacity = (spec.capacity or {}).get("storage", "") if spec else ""
        claim = spec.claim_ref if spec else None
        out.append(
            {
                "name": _s(pv.metadata.name),
                "capacity": _s(capacity, 32),
                "status": _s(status.phase if status else "", 32),
                "claim": _s(f"{claim.namespace}/{claim.name}" if claim else "", 128),
                "storage_class": _s(spec.storage_class_name if spec else "", 64),
                "age": age_of(pv.metadata.creation_timestamp),
            }
        )
    return out


def list_storageclasses(conn: Any) -> list[dict]:
    """[READ] List storage classes (name, provisioner, reclaim policy, default)."""
    result = call(conn.storage.list_storage_class, path="storageclasses")
    out: list[dict] = []
    default_anno = "storageclass.kubernetes.io/is-default-class"
    for sc in result.items or []:
        annotations = sc.metadata.annotations or {}
        out.append(
            {
                "name": _s(sc.metadata.name),
                "provisioner": _s(sc.provisioner, 128),
                "reclaim_policy": _s(sc.reclaim_policy, 32),
                "volume_binding_mode": _s(sc.volume_binding_mode, 32),
                "default": annotations.get(default_anno) == "true",
                "age": age_of(sc.metadata.creation_timestamp),
            }
        )
    return out
