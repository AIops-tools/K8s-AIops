"""Configuration management for k8s-aiops.

Loads connection targets from a YAML config file. A target selects a kube
context from a kubeconfig (and optionally a default namespace and an explicit
kubeconfig path). Credentials are NOT stored here — the kubeconfig holds them
(client certs, tokens, exec plugins for EKS/GKE/AKS). The harness still checks
that the state directory ``~/.k8s-aiops`` is owner-only (chmod 700).
"""

from __future__ import annotations

import logging
import stat
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".k8s-aiops"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

_log = logging.getLogger("k8s-aiops.config")


def _check_dir_permissions() -> None:
    """Warn if the config dir is accessible beyond the owner (should be 700)."""
    if not CONFIG_DIR.exists():
        return
    try:
        mode = CONFIG_DIR.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            _log.warning(
                "Security warning: %s has permissions %s (should be 700). "
                "Run: chmod 700 %s",
                CONFIG_DIR,
                oct(stat.S_IMODE(mode)),
                CONFIG_DIR,
            )
    except OSError:
        pass


_check_dir_permissions()


@dataclass(frozen=True)
class TargetConfig:
    """A Kubernetes connection target.

    ``context`` names a context inside the kubeconfig; omit to use the
    kubeconfig's current-context. ``namespace`` is an optional default for
    namespaced operations. ``kubeconfig`` is an optional explicit path
    (otherwise ``KUBECONFIG`` / ``~/.kube/config`` are used). No secrets here.
    """

    name: str
    context: str | None = None
    namespace: str | None = None
    kubeconfig: str | None = None

    @property
    def context_key(self) -> str:
        """Stable cache key identifying this target's client (context+config)."""
        return f"{self.kubeconfig or '~/.kube/config'}::{self.context or 'current'}"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application config."""

    targets: tuple[TargetConfig, ...] = ()

    def get_target(self, name: str) -> TargetConfig:
        for t in self.targets:
            if t.name == name:
                return t
        available = ", ".join(t.name for t in self.targets) or "(none)"
        raise KeyError(f"Target '{name}' not found. Available: {available}")

    @property
    def default_target(self) -> TargetConfig:
        if not self.targets:
            raise ValueError("No targets configured. Check config.yaml")
        return self.targets[0]


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML.

    Falls back to a single implicit "default" target (current kube-context) if
    no config file exists — so a freshly-installed agent can talk to whatever
    ``kubectl`` already points at without writing config first.
    """
    path = config_path or CONFIG_FILE
    if not path.exists():
        return AppConfig(targets=(TargetConfig(name="default"),))

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    targets = tuple(
        TargetConfig(
            name=t["name"],
            context=t.get("context"),
            namespace=t.get("namespace"),
            kubeconfig=t.get("kubeconfig"),
        )
        for t in raw.get("targets", [])
    )
    if not targets:
        targets = (TargetConfig(name="default"),)

    return AppConfig(targets=targets)
