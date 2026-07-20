"""Namespace operations: listing (read) plus create/delete (writes).

All API-returned text is run through ``sanitize()``.

``delete_namespace`` is the most destructive tool in this skill — it deletes
every object in the namespace and has no undo. Two refusals stand in front of
it, both enforced by the single ``guard_delete_namespace()`` function so the
CLI, the MCP tool and the dry-run preview can never disagree about what would
happen:

  * :class:`SelfLockout` — the target namespace is where this connection's own
    ServiceAccount credential lives. Deleting it revokes the credential, and
    this write has no undo to fail: the tool simply stops working. **Not
    overridable.**
  * :class:`ProtectedNamespace` — the target is one of the cluster's own
    control-plane namespaces. Overridable with ``confirm=True``, because an
    operator with a reason (a torn-down test cluster, a namespace stuck
    Terminating) must still be able to proceed deliberately.

Both are exact — only the namespace actually named is ever refused — and the
self-lockout one fails open: when the credential's namespace cannot be
determined the call proceeds, because an unknown identity must never be read as
"it is me".
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.connection import credential_namespace
from k8s_aiops.governance import opt_str, sanitize
from k8s_aiops.ops._shared import age_of, call

# Deleting any of these takes the cluster's own control plane with it: CoreDNS
# and kube-proxy (kube-system), the cluster-info bootstrap config (kube-public),
# or every node's heartbeat lease (kube-node-lease). The apiserver itself is a
# static pod and survives, which is exactly what makes this recoverable enough
# to be worth gating rather than forbidding outright.
PROTECTED_NAMESPACES = frozenset({"kube-system", "kube-public", "kube-node-lease"})


class SelfLockout(ValueError):  # noqa: N818 — teaching error, reads as a statement
    """Refused: the delete would revoke the credential this tool authenticates with."""


class ProtectedNamespace(ValueError):  # noqa: N818 — teaching error, reads as a statement
    """Refused: the namespace runs the cluster's control plane; pass confirm=True."""


def list_namespaces(conn: Any) -> list[dict]:
    """[READ] List namespaces (name, status/phase, age)."""
    result = call(conn.core.list_namespace, path="namespaces")
    out: list[dict] = []
    for ns in result.items or []:
        out.append(
            {
                "name": opt_str(ns.metadata.name, 128),
                "phase": opt_str(ns.status.phase if ns.status else None, 32),
                "age": age_of(ns.metadata.creation_timestamp),
            }
        )
    return out


def create_namespace(conn: Any, name: str) -> dict:
    """[WRITE] Create a namespace. Inverse: delete_namespace."""
    body = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": name}}
    call(conn.core.create_namespace, body, path="namespaces")
    return {"name": sanitize(name, 128), "action": "created"}


def guard_delete_namespace(name: str, *, confirm: bool = False, target: Any = None) -> None:
    """Raise whatever ``delete_namespace`` would raise, without deleting anything.

    Called by ``delete_namespace`` itself *and* by the MCP wrapper ahead of its
    ``dry_run`` early return, so a preview of a refused delete reports the refusal
    instead of a green ``wouldDelete``. Both paths run this one function, so the
    preview and the real call can never disagree.

    Takes the ``TargetConfig`` rather than a live connection because the only
    identity fact it needs is in the kubeconfig on disk. That keeps the guard
    reachable from the preview path without building an API client or contacting
    the apiserver — a dry run may read, but it must never write.

    ``target=None`` skips the self-lockout check (nothing to read an identity
    from); the protected-namespace check is a pure name comparison and always
    runs.
    """
    if target is not None:
        own = credential_namespace(target)
        if own is not None and own == name:
            raise SelfLockout(
                f"Refusing to delete namespace '{name}': it holds the ServiceAccount "
                f"this tool authenticates as. Deleting it destroys the credential "
                f"mid-request, and delete_namespace has no undo — every later call "
                f"fails until someone re-issues a kubeconfig by hand. This refusal is "
                f"deliberately not overridable by confirm. Point --target at a context "
                f"whose credential lives elsewhere (a cluster-admin kubeconfig, or a "
                f"ServiceAccount in another namespace) and run it from there."
            )
    if name in PROTECTED_NAMESPACES and not confirm:
        raise ProtectedNamespace(
            f"Refusing to delete namespace '{name}': it runs the cluster's control "
            f"plane (CoreDNS, kube-proxy, the CNI and every node heartbeat live in "
            f"these). Deleting it breaks all DNS and pod networking cluster-wide, and "
            f"there is no undo. If you are tearing this cluster down on purpose, or "
            f"the namespace is stuck Terminating, re-run with confirm=true "
            f"(CLI: --confirm). Protected: {', '.join(sorted(PROTECTED_NAMESPACES))}."
        )


def delete_namespace(conn: Any, name: str, confirm: bool = False) -> dict:
    """[WRITE] Delete a namespace and EVERYTHING in it. HIGH RISK — no undo.

    Refuses two targets (see ``guard_delete_namespace``): the namespace holding
    this connection's own ServiceAccount credential — an operation that destroys
    its own reversibility, never overridable — and the cluster's control-plane
    namespaces, which ``confirm=True`` unlocks for a deliberate teardown.
    """
    guard_delete_namespace(name, confirm=confirm, target=getattr(conn, "target", None))
    call(conn.core.delete_namespace, name, path=f"namespaces/{name}")
    return {"name": sanitize(name, 128), "action": "deleted"}
