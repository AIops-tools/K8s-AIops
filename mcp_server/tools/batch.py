"""MCP tools for batch workloads: jobs and cronjobs.

Reads are ``risk_level=low``. ``delete_job`` is a ``high`` write with no undo;
it takes ``dry_run: bool = False`` — a dry run returns a ``{"dryRun": True,
...}`` preview without touching the cluster.
"""

from typing import Optional

from k8s_aiops.governance import governed_tool
from k8s_aiops.ops import batch as ops
from mcp_server._shared import _get_connection, mcp, tool_errors


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def job_list(namespace: Optional[str] = None, target: Optional[str] = None) -> list:
    """[READ] List jobs (name, namespace, completions, succeeded/failed, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_jobs(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def job_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single job by name.

    Args:
        name: Job name (see job_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_job(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def cronjob_list(namespace: Optional[str] = None, target: Optional[str] = None) -> list:
    """[READ] List cronjobs (name, namespace, schedule, suspend, active, age).

    Args:
        namespace: Namespace; omit for all namespaces.
        target: k8s target name from config.
    """
    return ops.list_cronjobs(_get_connection(target), namespace)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def cronjob_get(
    name: str, namespace: Optional[str] = None, target: Optional[str] = None
) -> dict:
    """[READ] Return detail for a single cronjob by name.

    Args:
        name: CronJob name (see cronjob_list).
        namespace: Namespace; omit for the target's default namespace.
        target: k8s target name from config.
    """
    return ops.get_cronjob(_get_connection(target), name, namespace)


@mcp.tool()
@governed_tool(risk_level="high")
@tool_errors("dict")
def delete_job(
    name: str,
    namespace: Optional[str] = None,
    dry_run: bool = False,
    target: Optional[str] = None,
) -> dict:
    """[WRITE][risk=high] Delete a job and its pods. HIGH RISK — no undo.

    Pass dry_run=True to preview without deleting.

    Args:
        name: Job name.
        namespace: Namespace; omit for the target's default namespace.
        dry_run: If True, preview without deleting.
        target: k8s target name from config.
    """
    if dry_run:
        return {"dryRun": True, "wouldDelete": {"name": name, "namespace": namespace}}
    return ops.delete_job(_get_connection(target), name, namespace)
