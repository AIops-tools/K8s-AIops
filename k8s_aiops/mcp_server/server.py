"""MCP server wrapping k8s-aiops operations (stdio transport).

Thin adapter layer: each ``@mcp.tool()`` function (in ``k8s_aiops/mcp_server/tools/``)
delegates to the ``k8s_aiops`` ops package and is wrapped with the k8s-aiops
``@governed_tool`` harness (audit / budget / undo / risk-tier).

Standalone, self-governed Kubernetes operations (preview). Works with any
kubeconfig-reachable cluster (standard Kubernetes, k3s, EKS, GKE, AKS).

Source: https://github.com/AIops-tools/K8s-AIops
License: MIT
"""

import logging
import os

from k8s_aiops.mcp_server._annotations import apply_risk_annotations
from k8s_aiops.mcp_server._shared import _safe_error, mcp, tool_errors

# Importing the tool modules registers every @mcp.tool() onto the shared
# `mcp` instance. Order does not matter; each module is self-contained.
from k8s_aiops.mcp_server.tools import (  # noqa: F401 — side effects
    batch,
    cluster,
    config_resources,
    controllers,
    describe,
    diagnostics,
    lifecycle,
    metrics,
    namespaces,
    networking,
    nodes,
    rollout,
    storage,
    undo,
    workloads,
)

# Publish each tool's governance risk level as MCP annotations. Runs after
# every tool module has registered, so no tool is advertised unannotated.
apply_risk_annotations(mcp)

__all__ = ["mcp", "main", "_safe_error", "tool_errors"]

logger = logging.getLogger(__name__)



def main() -> None:
    """Run the MCP server over stdio."""
    logging.basicConfig(level=logging.INFO)
    # Read-only mode was removed. Warn a deployment that still exports the old
    # switch so it gets one audible signal instead of silently gaining writes.
    if os.environ.get("K8S_READ_ONLY"):
        logger.warning(
            "K8S_READ_ONLY is set but no longer has any effect — "
            "read-only mode was removed. Writes ARE enabled. Restrict them via "
            "the connecting account's permissions instead (a read-only socket / "
            "scope-limited token)."
        )
    mcp.run(transport="stdio")
