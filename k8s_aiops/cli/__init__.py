"""CLI package for k8s-aiops.

Re-exports ``app`` so the pyproject entry point
``k8s-aiops = "k8s_aiops.cli:app"`` works unchanged.
"""

from k8s_aiops.cli._root import app

__all__ = ["app"]
