"""Read-only namespace operations.

All API-returned text is run through ``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import sanitize
from k8s_aiops.ops._shared import age_of, call


def list_namespaces(conn: Any) -> list[dict]:
    """[READ] List namespaces (name, status/phase, age)."""
    result = call(conn.core.list_namespace, path="namespaces")
    out: list[dict] = []
    for ns in result.items or []:
        out.append(
            {
                "name": sanitize(ns.metadata.name, 128),
                "phase": sanitize(ns.status.phase if ns.status else "", 32),
                "age": age_of(ns.metadata.creation_timestamp),
            }
        )
    return out


def create_namespace(conn: Any, name: str) -> dict:
    """[WRITE] Create a namespace. Inverse: delete_namespace."""
    body = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}}
    call(conn.core.create_namespace, body, path="namespaces")
    return {"name": sanitize(name, 128), "action": "created"}


def delete_namespace(conn: Any, name: str) -> dict:
    """[WRITE] Delete a namespace and EVERYTHING in it. HIGH RISK — no undo."""
    call(conn.core.delete_namespace, name, path=f"namespaces/{name}")
    return {"name": sanitize(name, 128), "action": "deleted"}
