"""Read operations for config resources: ConfigMaps and Secrets.

SECURITY: ConfigMap values are configuration (returned). Secret VALUES are
never read, returned, or logged — ``secret_list`` returns only names, types,
and key NAMES. There is deliberately no ``secret_get`` that returns values.
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


def list_configmaps(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List configmaps (name, namespace, key count, age)."""
    if namespace:
        result = call(conn.core.list_namespaced_config_map, namespace, path="configmaps")
    else:
        result = call(conn.core.list_config_map_for_all_namespaces, path="configmaps")
    out: list[dict] = []
    for cm in result.items or []:
        keys = list((cm.data or {}).keys())
        out.append(
            {
                "name": _s(cm.metadata.name),
                "namespace": _s(cm.metadata.namespace, 64),
                "keys": len(keys),
                "age": age_of(cm.metadata.creation_timestamp),
            }
        )
    return out


def get_configmap(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return a configmap's data (keys + values — config, not secrets)."""
    ns = namespace or conn.default_namespace()
    cm = call(conn.core.read_namespaced_config_map, name, ns, path=f"configmaps/{name}")
    data = {_s(k, 128): _s(v, 2000) for k, v in (cm.data or {}).items()}
    return {
        "name": _s(name),
        "namespace": _s(ns, 64),
        "keys": sorted(data.keys()),
        "data": data,
        "age": age_of(cm.metadata.creation_timestamp),
    }


def list_secrets(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List secrets — names, types, and key NAMES only.

    SECURITY: secret VALUES are never read or returned (redacted by design).
    Only the metadata and the set of key names are exposed.
    """
    if namespace:
        result = call(conn.core.list_namespaced_secret, namespace, path="secrets")
    else:
        result = call(conn.core.list_secret_for_all_namespaces, path="secrets")
    out: list[dict] = []
    for secret in result.items or []:
        # Read the KEY NAMES only — never the values (secret.data is dropped).
        key_names = sorted(_s(k, 128) for k in (secret.data or {}).keys())
        out.append(
            {
                "name": _s(secret.metadata.name),
                "namespace": _s(secret.metadata.namespace, 64),
                "type": _s(secret.type, 64),
                "key_names": key_names,
                "values": "<redacted>",
                "age": age_of(secret.metadata.creation_timestamp),
            }
        )
    return out
