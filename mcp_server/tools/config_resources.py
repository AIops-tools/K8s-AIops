"""MCP tools for config resources: configmaps and secrets (all read-only).

SECURITY: ``secret_list`` returns names, types, and key NAMES only — secret
values are never read or returned. There is no tool that returns secret values.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import config_resources as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def configmap_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List configmaps (name, namespace, key count, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_configmaps(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def configmap_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return a configmap's data (keys + values — config, not secrets).

    Args:
        name: ConfigMap name (see configmap_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_configmap(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def secret_list(
    namespace: Optional[str] = None, target: Optional[str] = None
) -> list:
    """[READ] List secrets — names, types, and key NAMES only (values redacted).

    Secret VALUES are never returned. Use this to discover which secrets and
    keys exist, then mount/reference them via the kubeconfig-authorized workload.

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_secrets(_get_connection(target), namespace)
