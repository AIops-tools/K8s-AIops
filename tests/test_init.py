"""Tests for the ``k8s-aiops init`` onboarding wizard.

The wizard is driven end-to-end through Typer's CliRunner with every path
isolated under tmp_path: config.yaml under a monkeypatched CONFIG_DIR, and the
kubeconfig a synthetic two-context file pointed at by ``KUBECONFIG``. k8s-aiops
has no secret store — credentials stay in the kubeconfig — and it no longer
seeds a policy file, so there is nothing to seed or unlock here.
"""

from __future__ import annotations

import pytest
import yaml
from typer.testing import CliRunner

import k8s_aiops.cli.init as init_mod
import k8s_aiops.config as config_mod
import k8s_aiops.doctor as doctor_mod

KUBECONFIG_YAML = {
    "apiVersion": "v1",
    "kind": "Config",
    "current-context": "k3s-lab",
    "clusters": [
        {"name": "lab-cluster", "cluster": {"server": "https://127.0.0.1:6443"}},
        {"name": "eks-cluster", "cluster": {"server": "https://eks.example.com"}},
    ],
    "contexts": [
        {
            "name": "k3s-lab",
            "context": {"cluster": "lab-cluster", "user": "lab-admin", "namespace": "dev"},
        },
        {
            "name": "prod-eks",
            "context": {"cluster": "eks-cluster", "user": "eks-admin"},
        },
    ],
    "users": [
        {"name": "lab-admin", "user": {"token": "not-a-real-token"}},
        {"name": "eks-admin", "user": {"token": "not-a-real-token"}},
    ],
}

# Wizard answers: accept the current context (k3s-lab), accept its name as the
# target name, accept its default namespace (dev), no second context, decline
# the trailing doctor run.
WIZARD_INPUT = "\n\n\nn\nn\n"


@pytest.fixture
def init_home(tmp_path, monkeypatch):
    """Isolate config + governance home + kubeconfig under tmp_path."""
    config_file = tmp_path / "config.yaml"
    monkeypatch.setenv("K8S_AIOPS_HOME", str(tmp_path))  # isolate the governance home
    monkeypatch.setattr(init_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(init_mod, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", config_file)
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text(yaml.safe_dump(KUBECONFIG_YAML), "utf-8")
    _point_kubeconfig_at(monkeypatch, kubeconfig)
    return tmp_path


def _point_kubeconfig_at(monkeypatch, path) -> None:
    """Point the kubernetes client at ``path`` for kubeconfig discovery.

    KUBECONFIG alone is not enough: the client freezes it into
    ``KUBE_CONFIG_DEFAULT_LOCATION`` at import time, so patch that too.
    """
    import kubernetes.config.kube_config as kube_config_mod

    monkeypatch.setenv("KUBECONFIG", str(path))
    monkeypatch.setattr(kube_config_mod, "KUBE_CONFIG_DEFAULT_LOCATION", str(path))


def _run_init(input_text: str = WIZARD_INPUT):
    from k8s_aiops.cli import app

    return CliRunner().invoke(app, ["init"], input=input_text)


def _targets(init_home) -> list[dict]:
    raw = yaml.safe_load((init_home / "config.yaml").read_text("utf-8"))
    return raw["targets"]


@pytest.mark.unit
def test_init_registers_current_context_with_its_default_namespace(init_home):
    result = _run_init()
    assert result.exit_code == 0, result.output
    assert _targets(init_home) == [
        {"name": "k3s-lab", "context": "k3s-lab", "namespace": "dev"}
    ]


@pytest.mark.unit
def test_init_context_selection_by_number(init_home):
    # Pick context 2 (prod-eks), name it "prod", skip namespace (no default).
    result = _run_init("2\nprod\n\nn\nn\n")
    assert result.exit_code == 0, result.output
    assert _targets(init_home) == [{"name": "prod", "context": "prod-eks"}]


@pytest.mark.unit
def test_init_config_lands_in_isolated_home_only(init_home):
    result = _run_init()
    assert result.exit_code == 0, result.output
    assert (init_home / "config.yaml").exists()
    # Wizard reports the isolated path (rich may wrap it, so unwrap first).
    assert str(init_home) in result.output.replace("\n", "")


@pytest.mark.unit
def test_init_writes_no_policy_rules(init_home):
    """The skill no longer authorizes, so init seeds no rules.yaml — a fresh
    install delivers full functionality and leaves permission to the account."""
    result = _run_init()
    assert result.exit_code == 0, result.output
    assert not (init_home / "rules.yaml").exists()


@pytest.mark.unit
def test_init_merges_new_target_with_existing_config(init_home):
    assert _run_init().exit_code == 0
    result = _run_init("2\nprod\n\nn\nn\n")
    assert result.exit_code == 0, result.output
    assert [t["name"] for t in _targets(init_home)] == ["k3s-lab", "prod"]


@pytest.mark.unit
def test_init_overwrite_existing_target_after_confirm(init_home):
    assert _run_init().exit_code == 0
    # Same context/name again: confirm overwrite, change namespace to "staging".
    result = _run_init("\n\ny\nstaging\nn\nn\n")
    assert result.exit_code == 0, result.output
    assert _targets(init_home) == [
        {"name": "k3s-lab", "context": "k3s-lab", "namespace": "staging"}
    ]


@pytest.mark.unit
def test_init_declined_overwrite_keeps_existing_target(init_home):
    assert _run_init().exit_code == 0
    result = _run_init("\n\nn\nn\nn\n")  # decline overwrite, no more contexts
    assert result.exit_code == 0, result.output
    assert _targets(init_home) == [
        {"name": "k3s-lab", "context": "k3s-lab", "namespace": "dev"}
    ]


@pytest.mark.unit
def test_init_without_kubeconfig_fails_with_friendly_hint(init_home, monkeypatch):
    _point_kubeconfig_at(monkeypatch, init_home / "nope" / "kubeconfig")
    result = _run_init()
    assert result.exit_code != 0
    assert "No kubeconfig found" in str(result.exception)
    assert not (init_home / "config.yaml").exists()


@pytest.mark.unit
def test_init_accepting_doctor_confirm_runs_doctor(init_home, monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(doctor_mod, "run_doctor", lambda: calls.append(True) or 0)
    # Empty last answer accepts the doctor confirm's default=True.
    result = _run_init("\n\n\nn\n\n")
    assert result.exit_code == 0, result.output
    assert calls == [True]
