"""delete_namespace's two refusals, on every path that can reach the delete.

Covered here:
  * ``credential_namespace()`` — which kubeconfig shapes yield an identity and
    which yield "unknown" (every non-ServiceAccount shape must fail open).
  * ``guard_delete_namespace()`` — the protected control-plane list (overridable
    with ``confirm``) and the self-lockout refusal (never overridable).
  * The three call paths: the ops function, the governed MCP tool including its
    ``dry_run`` preview, and the CLI including its ``--dry-run`` branch.

Exactness is asserted throughout: a namespace that is neither protected nor the
credential's own must still delete, or the guard has become a blanket refusal.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from unittest.mock import MagicMock

import pytest
import yaml
from typer.testing import CliRunner

import k8s_aiops.governance.audit as audit_mod
import k8s_aiops.governance.policy as policy_mod
import k8s_aiops.governance.undo as undo_mod
from k8s_aiops.config import TargetConfig
from k8s_aiops.connection import credential_namespace
from k8s_aiops.ops import namespaces as ops
from k8s_aiops.ops.namespaces import ProtectedNamespace, SelfLockout

# ── kubeconfig builders ──────────────────────────────────────────────────────


def _jwt(claims: dict) -> str:
    """A JWT-shaped token carrying ``claims`` (unsigned — nothing verifies it)."""
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.not-a-real-signature"


def _sa_token(namespace: str, name: str = "k8s-aiops") -> str:
    return _jwt({"sub": f"system:serviceaccount:{namespace}:{name}"})


def _kubeconfig(tmp_path, user: dict, *, context_namespace: str | None = None):
    """Write a one-context kubeconfig backed by ``user`` and return a TargetConfig."""
    context: dict = {"cluster": "c", "user": "u"}
    if context_namespace is not None:
        context["namespace"] = context_namespace
    doc = {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": "ctx",
        "clusters": [{"name": "c", "cluster": {"server": "https://cluster:6443"}}],
        "contexts": [{"name": "ctx", "context": context}],
        "users": [{"name": "u", "user": user}],
    }
    path = tmp_path / "kubeconfig"
    path.write_text(yaml.safe_dump(doc))
    return TargetConfig(name="t", kubeconfig=str(path))


# ── credential_namespace: what counts as a known identity ────────────────────


@pytest.mark.unit
def test_service_account_token_yields_its_namespace(tmp_path):
    target = _kubeconfig(tmp_path, {"token": _sa_token("observability")})
    assert credential_namespace(target) == "observability"


@pytest.mark.unit
def test_legacy_service_account_claim_yields_its_namespace(tmp_path):
    """Pre-1.21 tokens carry the namespace in a flat claim, not in 'sub'."""
    token = _jwt({"kubernetes.io/serviceaccount/namespace": "legacy-ns"})
    assert credential_namespace(_kubeconfig(tmp_path, {"token": token})) == "legacy-ns"


@pytest.mark.unit
def test_bound_token_namespace_claim_yields_its_namespace(tmp_path):
    """Projected/bound tokens nest the namespace under a 'kubernetes.io' object."""
    token = _jwt({"kubernetes.io": {"namespace": "bound-ns"}})
    assert credential_namespace(_kubeconfig(tmp_path, {"token": token})) == "bound-ns"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "user"),
    [
        ("client-certificate", {"client-certificate": "/tmp/c.crt", "client-key": "/k"}),
        ("client-certificate-data", {"client-certificate-data": "YWJj"}),
        ("exec plugin (EKS/GKE/AKS)", {"exec": {"command": "aws"}}),
        ("auth-provider", {"auth-provider": {"name": "gcp"}}),
        ("opaque bearer token", {"token": "not-a-jwt-at-all"}),
        ("no credential at all", {}),
    ],
    ids=["cert", "cert-data", "exec", "auth-provider", "opaque-token", "empty"],
)
def test_non_service_account_credentials_are_unknown(tmp_path, label, user):
    """None of these are namespace-bound, so none can be revoked by a delete."""
    assert credential_namespace(_kubeconfig(tmp_path, user)) is None, label


@pytest.mark.unit
def test_missing_kubeconfig_is_unknown_not_a_crash(tmp_path):
    target = TargetConfig(name="t", kubeconfig=str(tmp_path / "does-not-exist"))
    assert credential_namespace(target) is None


@pytest.mark.unit
def test_unreadable_kubeconfig_is_unknown_not_a_crash(tmp_path):
    path = tmp_path / "kubeconfig"
    path.write_text("{{{ not: valid: yaml")
    assert credential_namespace(TargetConfig(name="t", kubeconfig=str(path))) is None


@pytest.mark.unit
def test_context_namespace_alone_is_not_treated_as_the_credential_namespace(tmp_path):
    """A context's 'namespace:' is a default for commands, not a credential binding.

    Reading it as identity would refuse a cluster-admin's safe delete of whatever
    namespace they happened to be scoped to — a false positive the guard must not
    have.
    """
    target = _kubeconfig(
        tmp_path, {"client-certificate-data": "YWJj"}, context_namespace="platform"
    )
    assert credential_namespace(target) is None


# ── guard: protected control-plane namespaces (confirm overrides) ────────────


@pytest.mark.unit
@pytest.mark.parametrize("name", ["kube-system", "kube-public", "kube-node-lease"])
def test_protected_namespace_is_refused(name):
    with pytest.raises(ProtectedNamespace) as excinfo:
        ops.guard_delete_namespace(name)
    assert name in str(excinfo.value)
    assert "confirm" in str(excinfo.value)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["kube-system", "kube-public", "kube-node-lease"])
def test_confirm_overrides_the_protected_namespace_refusal(name):
    """Not a flat refusal — a deliberate operator must still be able to proceed."""
    ops.guard_delete_namespace(name, confirm=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name", ["staging", "kube", "kube-systems", "my-kube-system", "default", "prod"]
)
def test_unprotected_namespaces_pass_the_guard(name):
    """Exactness: only the three names are protected — no prefix/substring match."""
    ops.guard_delete_namespace(name)


# ── guard: self-lockout (never overridable) ──────────────────────────────────


@pytest.mark.unit
def test_deleting_own_service_account_namespace_is_refused(tmp_path):
    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    with pytest.raises(SelfLockout) as excinfo:
        ops.guard_delete_namespace("aiops", target=target)
    assert "aiops" in str(excinfo.value)


@pytest.mark.unit
def test_confirm_does_not_override_self_lockout(tmp_path):
    """confirm means 'I accept the blast radius', not 'revoke my own credential'.

    No operator intent makes the credential survive its own namespace's deletion,
    and this write has no undo to fall back on.
    """
    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    with pytest.raises(SelfLockout):
        ops.guard_delete_namespace("aiops", confirm=True, target=target)


@pytest.mark.unit
def test_other_namespaces_pass_when_credential_is_a_service_account(tmp_path):
    """Exactness: holding an SA credential must not block every other delete."""
    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    ops.guard_delete_namespace("staging", target=target)


@pytest.mark.unit
def test_unknown_identity_fails_open(tmp_path):
    """A cert-based context has no namespace-bound identity — the delete proceeds.

    Unknown must never read as "it is me": that would refuse deletes the tool has
    no evidence against.
    """
    target = _kubeconfig(tmp_path, {"client-certificate-data": "YWJj"})
    ops.guard_delete_namespace("aiops", target=target)


@pytest.mark.unit
def test_absent_target_skips_the_self_check_but_still_protects(tmp_path):
    ops.guard_delete_namespace("staging", target=None)
    with pytest.raises(ProtectedNamespace):
        ops.guard_delete_namespace("kube-system", target=None)


# ── ops layer: the refusal happens before the client call ────────────────────


def _conn(target=None) -> MagicMock:
    conn = MagicMock(name="conn")
    conn.target = target
    return conn


@pytest.mark.unit
def test_ops_delete_refuses_protected_without_calling_the_client():
    conn = _conn()
    with pytest.raises(ProtectedNamespace):
        ops.delete_namespace(conn, "kube-system")
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_ops_delete_refuses_self_namespace_without_calling_the_client(tmp_path):
    conn = _conn(_kubeconfig(tmp_path, {"token": _sa_token("aiops")}))
    with pytest.raises(SelfLockout):
        ops.delete_namespace(conn, "aiops")
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_ops_delete_proceeds_for_an_ordinary_namespace(tmp_path):
    conn = _conn(_kubeconfig(tmp_path, {"token": _sa_token("aiops")}))
    result = ops.delete_namespace(conn, "staging")
    assert result == {"name": "staging", "action": "deleted"}
    assert conn.core.delete_namespace.call_args.args == ("staging",)


@pytest.mark.unit
def test_ops_delete_proceeds_for_protected_when_confirmed():
    conn = _conn()
    assert ops.delete_namespace(conn, "kube-system", confirm=True)["action"] == "deleted"
    conn.core.delete_namespace.assert_called_once()


# ── MCP layer, including the dry-run preview ─────────────────────────────────


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("K8S_AIOPS_HOME", str(tmp_path / "home"))
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield tmp_path / "home"
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


def _patch_mcp(monkeypatch, target=None) -> MagicMock:
    """Point the MCP namespace tool at a mock client and a chosen target config."""
    from mcp_server.tools import namespaces as gov

    conn = _conn(target)
    monkeypatch.setattr(gov, "_get_connection", lambda t=None: conn)
    monkeypatch.setattr(gov, "_get_target_config", lambda t=None: target)
    return conn


@pytest.mark.unit
def test_mcp_delete_refuses_protected_namespace(gov_home, monkeypatch):
    from mcp_server.tools import namespaces as gov

    conn = _patch_mcp(monkeypatch)
    result = gov.delete_namespace(name="kube-system")
    assert "Refusing to delete namespace 'kube-system'" in result["error"]
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_mcp_delete_allows_protected_namespace_with_confirm(gov_home, monkeypatch):
    from mcp_server.tools import namespaces as gov

    conn = _patch_mcp(monkeypatch)
    result = gov.delete_namespace(name="kube-system", confirm=True)
    assert result["action"] == "deleted"
    conn.core.delete_namespace.assert_called_once()


@pytest.mark.unit
def test_mcp_dry_run_reports_the_refusal_instead_of_a_green_preview(gov_home, monkeypatch):
    """The bug this guard shape prevents: a preview that promises a delete the
    real call would reject. The guard runs BEFORE the dry_run early return."""
    from mcp_server.tools import namespaces as gov

    conn = _patch_mcp(monkeypatch)
    result = gov.delete_namespace(name="kube-system", dry_run=True)

    assert "wouldDelete" not in result
    assert "Refusing to delete namespace 'kube-system'" in result["error"]
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_mcp_dry_run_reports_self_lockout(gov_home, monkeypatch, tmp_path):
    from mcp_server.tools import namespaces as gov

    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    conn = _patch_mcp(monkeypatch, target)
    result = gov.delete_namespace(name="aiops", dry_run=True)

    assert "wouldDelete" not in result
    assert "ServiceAccount this tool authenticates as" in result["error"]
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_mcp_dry_run_still_previews_an_ordinary_namespace(gov_home, monkeypatch, tmp_path):
    """Exactness on the preview path too — the guard must not blanket-refuse."""
    from mcp_server.tools import namespaces as gov

    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    conn = _patch_mcp(monkeypatch, target)
    result = gov.delete_namespace(name="staging", dry_run=True)

    assert result == {"dryRun": True, "wouldDelete": {"name": "staging"}}
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_mcp_dry_run_preview_honours_confirm(gov_home, monkeypatch):
    from mcp_server.tools import namespaces as gov

    _patch_mcp(monkeypatch)
    result = gov.delete_namespace(name="kube-system", dry_run=True, confirm=True)
    assert result == {"dryRun": True, "wouldDelete": {"name": "kube-system"}}


@pytest.mark.unit
def test_refused_delete_is_audited_as_an_error(gov_home, monkeypatch):
    """A refusal is a governed outcome: it must leave a trail, not vanish.

    Recorded as ``error``, not ``ok`` — the audit-fidelity rule is that anything
    ``@tool_errors`` flattened into an ``{"error": ...}`` dict is a failed call,
    so a refused delete can never be read back as a delete that happened.
    """
    from mcp_server.tools import namespaces as gov

    _patch_mcp(monkeypatch)
    gov.delete_namespace(name="kube-system")

    conn = sqlite3.connect(gov_home / "audit.db")
    try:
        rows = conn.execute("SELECT tool, status FROM audit_log").fetchall()
    finally:
        conn.close()
    assert rows == [("delete_namespace", "error")]


# ── CLI, including its own --dry-run branch ──────────────────────────────────


@pytest.mark.unit
def test_cli_delete_refuses_protected_namespace(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    _patch_mcp(monkeypatch)
    monkeypatch.setattr("k8s_aiops.cli.namespace.get_target_config", lambda t=None: None)
    result = CliRunner().invoke(app, ["namespace", "delete", "kube-system"], input="y\ny\n")

    assert result.exit_code == 1
    assert "Refusing to delete namespace 'kube-system'" in result.output


@pytest.mark.unit
def test_cli_dry_run_refuses_protected_namespace(gov_home, monkeypatch):
    """The CLI --dry-run branch routes through the governed tool, so the guard
    runs inside it — otherwise a preview would green-light a refused delete.

    The refusal is a governed outcome, so it is audited as an error too: a
    preview that was refused can never be read back as a preview that passed.
    """
    from k8s_aiops.cli import app

    conn = _patch_mcp(monkeypatch)
    result = CliRunner().invoke(app, ["namespace", "delete", "kube-system", "--dry-run"])

    assert result.exit_code == 1
    assert "DRY-RUN" not in result.output
    assert "Refusing to delete namespace 'kube-system'" in result.output
    conn.core.delete_namespace.assert_not_called()

    db = sqlite3.connect(gov_home / "audit.db")
    try:
        assert db.execute("SELECT tool, status FROM audit_log").fetchall() == [
            ("delete_namespace", "error")
        ]
    finally:
        db.close()


@pytest.mark.unit
def test_cli_dry_run_refuses_a_self_lockout_namespace(gov_home, monkeypatch, tmp_path):
    """The other refusal, reached the same way — and not overridable by --confirm."""
    from k8s_aiops.cli import app

    target = _kubeconfig(tmp_path, {"token": _sa_token("aiops")})
    conn = _patch_mcp(monkeypatch, target)
    result = CliRunner().invoke(
        app, ["namespace", "delete", "aiops", "--dry-run", "--confirm"]
    )

    assert result.exit_code == 1
    assert "DRY-RUN" not in result.output
    assert "Refusing to delete namespace 'aiops'" in result.output
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_cli_dry_run_still_previews_an_ordinary_namespace(gov_home, monkeypatch):
    """Exactness: the guard must not blanket-refuse, and the allowed preview
    still renders the ordinary banner — now carrying the resolved payload."""
    from k8s_aiops.cli import app

    conn = _patch_mcp(monkeypatch)
    result = CliRunner().invoke(app, ["namespace", "delete", "staging", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    assert "name = staging" in result.output
    conn.core.delete_namespace.assert_not_called()


@pytest.mark.unit
def test_cli_confirm_flag_allows_a_protected_delete(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_mcp(monkeypatch)
    monkeypatch.setattr("k8s_aiops.cli.namespace.get_target_config", lambda t=None: None)
    result = CliRunner().invoke(
        app, ["namespace", "delete", "kube-system", "--confirm"], input="y\ny\n"
    )

    assert result.exit_code == 0, result.output
    conn.core.delete_namespace.assert_called_once()
