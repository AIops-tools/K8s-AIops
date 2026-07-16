"""Tests for ``run_doctor`` — environment and connectivity diagnostics.

Everything is redirected to a tmp dir: config.yaml under a monkeypatched
CONFIG_DIR, the kubeconfig is a synthetic file pointed at by ``KUBECONFIG``,
and the connection layer is faked at the ``ConnectionManager`` boundary — no
test ever touches a real cluster or ``~/.k8s-aiops``. (k8s-aiops has no secret
store: authentication is delegated entirely to the kubeconfig.)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from rich.console import Console

import k8s_aiops.config as config_mod
import k8s_aiops.connection as connection_mod
import k8s_aiops.doctor as doctor_mod
from k8s_aiops.doctor import run_doctor

KUBECONFIG_YAML = {
    "apiVersion": "v1",
    "kind": "Config",
    "current-context": "k3s-lab",
    "clusters": [
        {"name": "lab-cluster", "cluster": {"server": "https://127.0.0.1:6443"}},
    ],
    "contexts": [
        {
            "name": "k3s-lab",
            "context": {"cluster": "lab-cluster", "user": "lab-admin", "namespace": "dev"},
        },
    ],
    "users": [{"name": "lab-admin", "user": {"token": "not-a-real-token"}}],
}


@pytest.fixture
def doctor_home(tmp_path, monkeypatch):
    """Isolate config + governance home + kubeconfig under tmp_path."""
    config_file = tmp_path / "config.yaml"
    monkeypatch.setenv("K8S_AIOPS_HOME", str(tmp_path))
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(doctor_mod, "CONFIG_FILE", config_file)
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text(yaml.safe_dump(KUBECONFIG_YAML), "utf-8")
    _point_kubeconfig_at(monkeypatch, kubeconfig)
    # Wide console so long messages don't wrap mid-assertion.
    monkeypatch.setattr(doctor_mod, "_console", Console(width=500))
    return tmp_path


def _point_kubeconfig_at(monkeypatch, path) -> None:
    """Point the kubernetes client at ``path`` for kubeconfig discovery.

    KUBECONFIG alone is not enough: the client freezes it into
    ``KUBE_CONFIG_DEFAULT_LOCATION`` at import time, so patch that too.
    """
    import kubernetes.config.kube_config as kube_config_mod

    monkeypatch.setenv("KUBECONFIG", str(path))
    monkeypatch.setattr(kube_config_mod, "KUBE_CONFIG_DEFAULT_LOCATION", str(path))


def _write_config(tmp_path, targets: list[dict]) -> None:
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"targets": targets}), "utf-8")


class _HealthyManager:
    """Stands in for ConnectionManager: every connect() succeeds."""

    def __init__(self, config) -> None:
        self._config = config

    def connect(self, name):
        conn = MagicMock(name=f"conn-{name}")
        conn.version.get_code.return_value = SimpleNamespace(git_version="v1.30.2+k3s1")
        return conn


class _UnreachableManager:
    """Stands in for ConnectionManager: every connect() fails."""

    def __init__(self, config) -> None:
        self._config = config

    def connect(self, name):
        raise ConnectionError("dial tcp 127.0.0.1:6443: connection refused")


@pytest.mark.unit
def test_doctor_no_config_falls_back_to_current_context_with_init_hint(
    doctor_home, capsys
):
    """Missing config is not fatal — the implicit default target is used and the
    operator is pointed at 'k8s-aiops init'."""
    assert run_doctor(skip_auth=True) == 0
    out = capsys.readouterr().out
    assert "No config file" in out
    assert "k8s-aiops init" in out
    assert "1 target(s) configured" in out


@pytest.mark.unit
def test_doctor_config_load_failure_reported_not_raised(doctor_home, capsys):
    (doctor_home / "config.yaml").write_text("targets: [unclosed", "utf-8")
    assert run_doctor() == 1
    assert "Config load failed" in capsys.readouterr().out


@pytest.mark.unit
def test_doctor_healthy_reports_context_and_server_version(
    doctor_home, monkeypatch, capsys
):
    _write_config(doctor_home, [{"name": "lab", "context": "k3s-lab"}])
    monkeypatch.setattr(connection_mod, "ConnectionManager", _HealthyManager)
    assert run_doctor() == 0
    out = capsys.readouterr().out
    assert "Config file present" in out
    assert "Context 'k3s-lab' found for target 'lab'" in out
    assert "Reachable 'lab'" in out
    assert "v1.30.2+k3s1" in out  # server version comes from the version API


@pytest.mark.unit
def test_doctor_flags_context_missing_from_kubeconfig(doctor_home, capsys):
    _write_config(doctor_home, [{"name": "lab", "context": "gone-cluster"}])
    assert run_doctor(skip_auth=True) == 1
    out = capsys.readouterr().out
    assert "references context 'gone-cluster'" in out
    assert "not in the kubeconfig" in out


@pytest.mark.unit
def test_doctor_missing_kubeconfig_warns_but_does_not_crash(
    doctor_home, monkeypatch, capsys
):
    """A broken/missing kubeconfig is a reported status, never a traceback."""
    _point_kubeconfig_at(monkeypatch, doctor_home / "nope" / "kubeconfig")
    _write_config(doctor_home, [{"name": "lab", "context": "k3s-lab"}])
    assert run_doctor(skip_auth=True) == 0
    assert "Could not read kubeconfig contexts" in capsys.readouterr().out


@pytest.mark.unit
def test_doctor_unreachable_cluster_exit_one(doctor_home, monkeypatch, capsys):
    _write_config(doctor_home, [{"name": "lab", "context": "k3s-lab"}])
    monkeypatch.setattr(connection_mod, "ConnectionManager", _UnreachableManager)
    assert run_doctor() == 1
    out = capsys.readouterr().out
    assert "Connect to 'lab' failed" in out
    assert "connection refused" in out


@pytest.mark.unit
def test_doctor_skip_auth_never_touches_the_connection_layer(
    doctor_home, monkeypatch, capsys
):
    _write_config(doctor_home, [{"name": "lab", "context": "k3s-lab"}])

    def _boom(config):  # doctor must not even construct a manager
        raise AssertionError("ConnectionManager must not be used with --skip-auth")

    monkeypatch.setattr(connection_mod, "ConnectionManager", _boom)
    assert run_doctor(skip_auth=True) == 0
    out = capsys.readouterr().out
    assert "Skipping connectivity check" in out
    assert "Reachable" not in out


@pytest.mark.unit
def test_cli_doctor_command_exits_with_doctor_code(doctor_home):
    from typer.testing import CliRunner

    from k8s_aiops.cli import app

    _write_config(doctor_home, [{"name": "lab", "context": "k3s-lab"}])
    result = CliRunner().invoke(app, ["doctor", "--skip-auth"])
    assert result.exit_code == 0, result.output
    assert "Skipping connectivity check" in result.output
