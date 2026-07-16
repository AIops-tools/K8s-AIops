"""dry_run=True on every MCP write tool: preview only, no client, no undo.

Each of the 15 write tools must, when called with ``dry_run=True``:
  1. return a ``{"dryRun": True, "wouldX": ...}`` preview,
  2. never touch the kubernetes client (``_get_connection`` is a tripwire),
  3. never record an undo descriptor (no ``_undo_id``, no undo.db row).

The calls still run through the real governance harness (bound to a temp
``K8S_AIOPS_HOME``), so a dry run remains policy-checked and audited.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import k8s_aiops.governance.audit as audit_mod
import k8s_aiops.governance.policy as policy_mod
import k8s_aiops.governance.undo as undo_mod
from mcp_server.tools import batch, controllers, lifecycle, namespaces, nodes, rollout


def _reset_singletons() -> None:
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("K8S_AIOPS_HOME", str(tmp_path))
    _reset_singletons()
    yield tmp_path
    _reset_singletons()


def _undo_rows(home) -> list:
    db = home / "undo.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT undo_tool FROM undo_log").fetchall()
    finally:
        conn.close()


def _tripwire(target=None):  # noqa: ARG001 — signature mirrors _get_connection
    raise AssertionError("dry_run must not touch the kubernetes client")


# (module, tool name, call kwargs, preview key) — all 15 MCP write tools.
WRITE_TOOLS = [
    (lifecycle, "scale_deployment", {"name": "web", "replicas": 5}, "wouldScale"),
    (lifecycle, "rollout_restart_deployment", {"name": "web"}, "wouldRestart"),
    (lifecycle, "delete_pod", {"name": "web-1"}, "wouldDelete"),
    (lifecycle, "delete_deployment", {"name": "web"}, "wouldDelete"),
    (controllers, "scale_statefulset", {"name": "db", "replicas": 3}, "wouldScale"),
    (batch, "delete_job", {"name": "migrate"}, "wouldDelete"),
    (nodes, "cordon_node", {"name": "node-1"}, "wouldCordon"),
    (nodes, "uncordon_node", {"name": "node-1"}, "wouldUncordon"),
    (nodes, "drain_node", {"name": "node-1"}, "wouldDrain"),
    (rollout, "rollout_undo_deployment", {"name": "web"}, "wouldRollBack"),
    (rollout, "rollout_pause", {"name": "web"}, "wouldPause"),
    (rollout, "rollout_resume", {"name": "web"}, "wouldResume"),
    (
        rollout,
        "set_deployment_image",
        {"name": "web", "container": "app", "image": "nginx:1.27"},
        "wouldSetImage",
    ),
    (namespaces, "create_namespace", {"name": "staging"}, "wouldCreate"),
    (namespaces, "delete_namespace", {"name": "staging"}, "wouldDelete"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("module", "tool", "kwargs", "would_key"),
    WRITE_TOOLS,
    ids=[t[1] for t in WRITE_TOOLS],
)
def test_dry_run_previews_without_client_or_undo(
    gov_home, monkeypatch, module, tool, kwargs, would_key
):
    monkeypatch.setattr(module, "_get_connection", _tripwire)
    result = getattr(module, tool)(dry_run=True, **kwargs)

    assert result.get("dryRun") is True, result
    assert would_key in result, result
    assert "error" not in result, result
    assert "_undo_id" not in result
    assert _undo_rows(gov_home) == []


@pytest.mark.unit
def test_dry_run_is_still_audited(gov_home, monkeypatch):
    """A preview is a governed call: it must land in the audit log as ok."""
    monkeypatch.setattr(lifecycle, "_get_connection", _tripwire)
    lifecycle.scale_deployment(name="web", replicas=5, dry_run=True)

    conn = sqlite3.connect(gov_home / "audit.db")
    try:
        rows = conn.execute("SELECT tool, status FROM audit_log").fetchall()
    finally:
        conn.close()
    assert rows == [("scale_deployment", "ok")]


@pytest.mark.unit
def test_drain_node_records_undo_only_for_real_run(gov_home, monkeypatch):
    """Contrast test for the guarded undo lambdas: drain_node's partial-inverse
    descriptor must be recorded for a real drain, and NOT for a dry run."""
    conn = MagicMock(name="conn")
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(nodes, "_get_connection", lambda target=None: conn)

    preview = nodes.drain_node(name="node-1", dry_run=True)
    assert preview["dryRun"] is True
    assert _undo_rows(gov_home) == []
    conn.core.patch_node.assert_not_called()

    real = nodes.drain_node(name="node-1")
    assert real.get("_undo_id")
    assert _undo_rows(gov_home) == [("uncordon_node",)]
    conn.core.patch_node.assert_called_once()


@pytest.mark.unit
def test_scale_deployment_dry_run_records_no_undo_but_real_run_does(gov_home, monkeypatch):
    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment_scale.return_value = SimpleNamespace(
        spec=SimpleNamespace(replicas=3)
    )
    monkeypatch.setattr(lifecycle, "_get_connection", lambda target=None: conn)

    preview = lifecycle.scale_deployment(name="web", replicas=5, dry_run=True)
    assert preview == {
        "dryRun": True,
        "wouldScale": {"name": "web", "namespace": None, "replicas": 5},
    }
    assert _undo_rows(gov_home) == []
    conn.apps.patch_namespaced_deployment_scale.assert_not_called()

    real = lifecycle.scale_deployment(name="web", replicas=5)
    assert real["previous_replicas"] == 3
    assert real.get("_undo_id")
    assert _undo_rows(gov_home) == [("scale_deployment",)]
