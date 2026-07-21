"""CLI write path — dry-run previews and confirmed writes, both governed.

The CLI write commands delegate execution to the ``@governed_tool`` functions
in ``mcp_server.tools``. These tests drive a write command PAST the confirm
prompts (double for high-risk delete, single for medium-risk scale/restart)
and assert the call really went through the governed path (audit row on disk)
— the regression test for the "CLI writes were unaudited" line-wide fix.

``--dry-run`` previews route through the same governed twin with
``dry_run=True``. The invariant they hold is **a dry_run MAY read; it must
never write**: the mutating kubernetes client method is never called, while the
audit row IS written. The older rule — that a preview reached no governed call
at all — made every guard unreachable from a preview, so a preview could
green-light an operation the real write then refused.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

import k8s_aiops.governance.audit as audit_mod
import k8s_aiops.governance.policy as policy_mod
import k8s_aiops.governance.undo as undo_mod


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("K8S_AIOPS_HOME", str(tmp_path))
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield tmp_path
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


def _audit_tools(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT tool FROM audit_log ORDER BY id")]
    finally:
        conn.close()


def _mock_conn() -> MagicMock:
    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = "default"
    conn.apps.delete_namespaced_deployment.return_value = None
    return conn


@pytest.mark.unit
def test_cli_deployment_delete_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _mock_conn()
    import mcp_server.tools.lifecycle as gov_lifecycle

    monkeypatch.setattr(gov_lifecycle, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["deployment", "delete", "web", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    # Richer than the old hand-written string: the governed twin's resolved
    # wouldDelete payload is what the banner reports.
    assert "name = web" in result.output
    conn.apps.delete_namespaced_deployment.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["delete_deployment"]


@pytest.mark.unit
def test_cli_deployment_delete_confirmed_goes_through_governance(gov_home, monkeypatch):
    """Confirmed CLI write must execute via the governed twin: the API call runs
    AND an audit row lands in audit.db (this is what the reroute fix bought)."""
    from k8s_aiops.cli import app

    conn = _mock_conn()
    import mcp_server.tools.lifecycle as gov_lifecycle

    monkeypatch.setattr(gov_lifecycle, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["deployment", "delete", "web"], input="y\ny\n")
    assert result.exit_code == 0, result.output
    conn.apps.delete_namespaced_deployment.assert_called_once()
    assert _audit_tools(gov_home / "audit.db") == ["delete_deployment"]


@pytest.mark.unit
def test_cli_deployment_delete_aborts_without_double_confirm(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _mock_conn()
    import mcp_server.tools.lifecycle as gov_lifecycle

    monkeypatch.setattr(gov_lifecycle, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["deployment", "delete", "web"], input="y\nn\n")
    assert result.exit_code != 0
    conn.apps.delete_namespaced_deployment.assert_not_called()
    assert not (gov_home / "audit.db").exists()


# ── medium-risk single-confirm commands: deployment scale / restart ──────────


def _patch_conn(monkeypatch) -> MagicMock:
    conn = _mock_conn()
    conn.apps.read_namespaced_deployment_scale.return_value = SimpleNamespace(
        spec=SimpleNamespace(replicas=3)
    )
    import mcp_server.tools.lifecycle as gov_lifecycle

    monkeypatch.setattr(gov_lifecycle, "_get_connection", lambda target=None: conn)
    return conn


@pytest.mark.unit
def test_cli_deployment_scale_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "scale", "web", "5", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "replicas = 5" in result.output
    conn.apps.patch_namespaced_deployment_scale.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["scale_deployment"]


@pytest.mark.unit
def test_cli_deployment_scale_confirmed_goes_through_governance(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "scale", "web", "5"], input="y\n")
    assert result.exit_code == 0, result.output
    conn.apps.patch_namespaced_deployment_scale.assert_called_once()
    assert _audit_tools(gov_home / "audit.db") == ["scale_deployment"]


@pytest.mark.unit
def test_cli_deployment_scale_declined_aborts_without_call(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "scale", "web", "5"], input="n\n")
    assert result.exit_code != 0
    conn.apps.patch_namespaced_deployment_scale.assert_not_called()
    assert not (gov_home / "audit.db").exists()


@pytest.mark.unit
def test_cli_deployment_restart_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "restart", "web", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.apps.patch_namespaced_deployment.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["rollout_restart_deployment"]


@pytest.mark.unit
def test_cli_deployment_restart_confirmed_goes_through_governance(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "restart", "web"], input="y\n")
    assert result.exit_code == 0, result.output
    conn.apps.patch_namespaced_deployment.assert_called_once()
    assert _audit_tools(gov_home / "audit.db") == ["rollout_restart_deployment"]


@pytest.mark.unit
def test_cli_deployment_restart_declined_aborts_without_call(gov_home, monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch)
    result = CliRunner().invoke(app, ["deployment", "restart", "web"], input="n\n")
    assert result.exit_code != 0
    conn.apps.patch_namespaced_deployment.assert_not_called()
    assert not (gov_home / "audit.db").exists()


# ── dry-run previews on the remaining write commands ────────────────────────
#
# Same invariant throughout: the preview routes through the governed twin, so
# it is audited and guard-checked, but the mutating kubernetes client method is
# never reached. Each test names the mutating method explicitly rather than
# settling for "the governed function was not called" — the thing that must not
# happen is the WRITE, not the call.


def _patch_gov(monkeypatch, module) -> MagicMock:
    """Point a governed tool module at a mock client; return it for assertions."""
    conn = _mock_conn()
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(module, "_get_connection", lambda target=None: conn)
    return conn


@pytest.mark.unit
def test_cli_node_drain_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import nodes as gov

    conn = _patch_gov(monkeypatch, gov)
    result = CliRunner().invoke(app, ["node", "drain", "node-a", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "name = node-a" in result.output
    conn.core.patch_node.assert_not_called()
    conn.core.create_namespaced_pod_eviction.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["drain_node"]


@pytest.mark.unit
def test_cli_node_cordon_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import nodes as gov

    conn = _patch_gov(monkeypatch, gov)
    result = CliRunner().invoke(app, ["node", "cordon", "node-a", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.core.patch_node.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["cordon_node"]


@pytest.mark.unit
def test_cli_pod_delete_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import lifecycle as gov

    conn = _patch_gov(monkeypatch, gov)
    result = CliRunner().invoke(app, ["pod", "delete", "web-1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.core.delete_namespaced_pod.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["delete_pod"]


@pytest.mark.unit
def test_cli_job_delete_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import batch as gov

    conn = _patch_gov(monkeypatch, gov)
    result = CliRunner().invoke(app, ["job", "delete", "backup", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.batch.delete_namespaced_job.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["delete_job"]


@pytest.mark.unit
def test_cli_namespace_delete_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import namespaces as gov

    conn = _patch_gov(monkeypatch, gov)
    monkeypatch.setattr(gov, "_get_target_config", lambda t=None: None)
    result = CliRunner().invoke(app, ["namespace", "delete", "payments", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.core.delete_namespace.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["delete_namespace"]


@pytest.mark.unit
def test_cli_rollout_undo_dry_run_reads_and_audits_but_never_writes(gov_home, monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import rollout as gov

    conn = _patch_gov(monkeypatch, gov)
    result = CliRunner().invoke(app, ["rollout", "undo", "web", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "to_revision = previous" in result.output
    conn.apps.patch_namespaced_deployment.assert_not_called()
    assert _audit_tools(gov_home / "audit.db") == ["rollout_undo_deployment"]
