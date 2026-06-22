"""Read-only workload MCP tools: pods, deployments, services, events, logs.

Every tool is wrapped with ``@governed_tool`` (the k8s-aiops harness): policy
pre-check, budget/runaway guard, graduated-autonomy risk-tier gate, and audit
logging to ~/.k8s-aiops/audit.db. These are all READ tools (no undo).
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import workloads as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pod_list(
    namespace: Optional[str] = None,
    label_selector: Optional[str] = None,
    target: Optional[str] = None,
) -> list:
    """[READ] List pods (name, namespace, phase, ready, restarts, node, age).

    Omit namespace to list across all namespaces. Use pod_get for full detail.

    Args:
        namespace: Namespace to scope to; omit for all namespaces.
        label_selector: Optional label selector, e.g. "app=web".
        target: k8s target name from config; omit to use the default.
    """
    return ops.list_pods(_get_connection(target), namespace, label_selector)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pod_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single pod by name.

    Args:
        name: Pod name (see pod_list).
        namespace: Namespace; omit to use the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_pod(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pod_logs(
    name: str,
    namespace: Optional[str] = None,
    tail_lines: int = 100,
    container: Optional[str] = None,
    target: Optional[str] = None,
) -> dict:
    """[READ] Return the most recent log lines for a pod (default 100).

    Args:
        name: Pod name.
        namespace: Namespace; omit for the target's default namespace.
        tail_lines: Number of trailing log lines to return.
        container: Container name (required only for multi-container pods).
        target: k8s target name from config.
    """
    return ops.get_pod_logs(_get_connection(target), name, namespace, tail_lines, container)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def deployment_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List deployments (name, namespace, desired/ready/available, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_deployments(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def deployment_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single deployment by name.

    Args:
        name: Deployment name (see deployment_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_deployment(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def service_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List services (name, namespace, type, cluster IP, ports).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_services(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def event_list(
    namespace: Optional[str] = None, limit: int = 50, target: Optional[str] = None
) -> list:
    """[READ] List recent events (type, reason, object, message, age).

    Useful for diagnosing why a pod is not starting (FailedScheduling, etc.).

    Args:
        namespace: Namespace; omit for all namespaces.
        limit: Maximum number of events to return.
        target: k8s target name from config.
    """
    return ops.list_events(_get_connection(target), namespace, limit)
