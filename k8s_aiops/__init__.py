"""k8s-aiops — governed Kubernetes operations for AI agents.

Standalone and self-contained: the governance harness (audit, token budget,
undo-token recording, a descriptive risk-tier label on each audit row, output
sanitize) is bundled under ``k8s_aiops.governance`` — this package has no
external skill-family dependency. Works with any kubeconfig-reachable cluster
(standard Kubernetes, k3s, EKS, GKE, AKS). Preview: not yet full-coverage.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("k8s-aiops")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0.0.0+unknown"
