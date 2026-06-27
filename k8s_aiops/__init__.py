"""k8s-aiops — governed Kubernetes operations for AI agents.

Standalone and self-contained: the governance harness (audit, token budget,
undo-token recording, graduated risk tiers, prompt-injection sanitize) is
bundled under ``k8s_aiops.governance`` — this package has no external
skill-family dependency. Works with any kubeconfig-reachable cluster
(standard Kubernetes, k3s, EKS, GKE, AKS). Preview: not yet full-coverage.
"""

__version__ = "0.2.0"
