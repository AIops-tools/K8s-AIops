"""Top-level Typer app: assembles sub-apps and top-level commands."""

from __future__ import annotations

import typer

from k8s_aiops.cli._common import NamespaceOption, TargetOption, cli_errors
from k8s_aiops.cli.cluster import api_resources_cmd, cluster_info_cmd
from k8s_aiops.cli.configmap import configmap_app, secret_app
from k8s_aiops.cli.daemonset import daemonset_app
from k8s_aiops.cli.deployment import deployment_app
from k8s_aiops.cli.diagnostics import diagnose_app
from k8s_aiops.cli.doctor import doctor_cmd
from k8s_aiops.cli.ingress import ingress_app
from k8s_aiops.cli.init import init_cmd
from k8s_aiops.cli.job import cronjob_app, job_app
from k8s_aiops.cli.namespace import namespace_app
from k8s_aiops.cli.node import node_app
from k8s_aiops.cli.pod import pod_app
from k8s_aiops.cli.rollout import rollout_app
from k8s_aiops.cli.service import service_app
from k8s_aiops.cli.statefulset import statefulset_app
from k8s_aiops.cli.storage import storage_app
from k8s_aiops.cli.top import top_app
from k8s_aiops.cli.undo import undo_app

app = typer.Typer(
    name="k8s-aiops",
    help="Governed Kubernetes operations for AI agents (works with k3s/EKS/GKE/AKS).",
    no_args_is_help=True,
)

app.add_typer(pod_app, name="pod")
app.add_typer(deployment_app, name="deployment")
app.add_typer(statefulset_app, name="statefulset")
app.add_typer(daemonset_app, name="daemonset")
app.add_typer(job_app, name="job")
app.add_typer(cronjob_app, name="cronjob")
app.add_typer(service_app, name="service")
app.add_typer(ingress_app, name="ingress")
app.add_typer(configmap_app, name="configmap")
app.add_typer(secret_app, name="secret")
app.add_typer(storage_app, name="storage")
app.add_typer(rollout_app, name="rollout")
app.add_typer(top_app, name="top")
app.add_typer(node_app, name="node")
app.add_typer(namespace_app, name="namespace")
app.add_typer(undo_app, name="undo")
app.add_typer(diagnose_app, name="diagnose")
app.command("init")(init_cmd)
app.command("doctor")(doctor_cmd)
app.command("cluster-info")(cluster_info_cmd)
app.command("api-resources")(api_resources_cmd)


@app.command("events")
@cli_errors
def events_cmd(
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    limit: int = typer.Option(50, "--limit", help="Maximum number of events to show"),
) -> None:
    """List recent cluster events (namespace-scoped or all-namespaces)."""
    from rich.console import Console
    from rich.table import Table

    from k8s_aiops.cli._common import get_connection
    from k8s_aiops.ops import workloads

    conn, _ = get_connection(target)
    result = workloads.list_events(conn, namespace, limit)
    table = Table(title="Kubernetes Events")
    for col in ("type", "reason", "object", "namespace", "message", "age"):
        table.add_column(col)
    for r in result["events"]:
        table.add_row(
            r["type"], r["reason"], r["object"], r["namespace"], r["message"], r["age"]
        )
    console_out = Console()
    console_out.print(table)
    if result["truncated"]:
        console_out.print(
            f"[yellow]Showing {result['returned']} of more than {result['limit']} "
            f"events — truncated, re-run with a higher --limit.[/yellow]"
        )


@app.command("mcp")
@cli_errors
def mcp_cmd() -> None:
    """Start the MCP server (stdio transport).

    Single-command entry point for MCP clients (does not go through uvx/PyPI
    resolution at launch):
        k8s-aiops mcp
    """
    import sys

    if sys.version_info < (3, 11):
        typer.echo(
            f"ERROR: k8s-aiops requires Python >= 3.11 "
            f"(got {sys.version_info.major}.{sys.version_info.minor}).\n"
            f"Fix: uv python install 3.12 && "
            f"uv tool install --python 3.12 --force k8s-aiops",
            err=True,
        )
        raise typer.Exit(2)

    from mcp_server.server import main as _mcp_main

    _mcp_main()


if __name__ == "__main__":
    app()
