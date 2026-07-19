"""Diagnostics / RCA MCP tools: pod health and workload readiness.

Read-only signature analyses (risk_level="low"). Each tool collects live
objects once and hands normalized rows to a pure analysis function in
``k8s_aiops.ops.diagnostics`` — so the heuristics stay unit-testable without a
live cluster, and the collection stays here where the connection is. The CLI
layer reuses ``collect_pod_rows`` / ``collect_workload_rows`` from this module
(the same CLI→mcp_server reuse the write commands already use).
"""

from typing import Any, Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import diagnostics as diag
from k8s_aiops.ops._shared import call
from mcp_server._shared import _get_connection, mcp, tool_errors

# (kind, namespaced list fn attr, all-namespaces list fn attr, path segment).
_WORKLOAD_KINDS = (
    ("Deployment", "list_namespaced_deployment", "list_deployment_for_all_namespaces",
     "deployments"),
    ("StatefulSet", "list_namespaced_stateful_set", "list_stateful_set_for_all_namespaces",
     "statefulsets"),
    ("DaemonSet", "list_namespaced_daemon_set", "list_daemon_set_for_all_namespaces",
     "daemonsets"),
)


def collect_pod_rows(
    conn: Any, namespace: Optional[str] = None, label_selector: Optional[str] = None
) -> list[dict]:
    """Fetch pods (namespace-scoped or all) and normalize to diagnostic rows."""
    kw: dict[str, Any] = {}
    if label_selector:
        kw["label_selector"] = label_selector
    if namespace:
        result = call(conn.core.list_namespaced_pod, namespace, path="pods", **kw)
    else:
        result = call(conn.core.list_pod_for_all_namespaces, path="pods", **kw)
    return [diag.pod_to_row(p) for p in (result.items or [])]


def collect_workload_rows(conn: Any, namespace: Optional[str] = None) -> list[dict]:
    """Fetch Deployments/StatefulSets/DaemonSets and normalize to rows."""
    rows: list[dict] = []
    for kind, ns_fn, all_fn, path in _WORKLOAD_KINDS:
        if namespace:
            result = call(getattr(conn.apps, ns_fn), namespace, path=path)
        else:
            result = call(getattr(conn.apps, all_fn), path=path)
        rows.extend(diag.workload_to_row(o, kind) for o in (result.items or []))
    return rows


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pod_health_rca(
    namespace: Optional[str] = None,
    label_selector: Optional[str] = None,
    target: Optional[str] = None,
) -> dict:
    """[READ] Scan pods for CrashLoopBackOff, image-pull failures, OOMKilled,
    unschedulable Pending pods, and high restart counts.

    Returns worst-first findings, each citing the reason string / restart count
    that tripped it plus a concrete kubectl action. Omit namespace to scan all.

    Args:
        namespace: Namespace to scope to; omit for all namespaces.
        label_selector: Optional label selector, e.g. "app=web".
        target: k8s target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    return diag.pod_health_findings(collect_pod_rows(conn, namespace, label_selector))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def workload_readiness_rca(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Scan Deployments/StatefulSets/DaemonSets for ready-vs-desired
    shortfalls, zero-ready outages, and rollout-stuck conditions.

    Returns worst-first findings, each citing the measured ready/desired ratio
    or the failing condition reason plus a concrete kubectl action.

    Args:
        namespace: Namespace to scope to; omit for all namespaces.
        target: k8s target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    return diag.workload_readiness_findings(collect_workload_rows(conn, namespace))
