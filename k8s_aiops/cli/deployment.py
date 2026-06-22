"""``k8s-aiops deployment ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    DryRunOption,
    NamespaceOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_print,
    get_connection,
)
from k8s_aiops.ops import lifecycle, workloads

deployment_app = typer.Typer(help="Deployment operations.", no_args_is_help=True)
console = Console()


@deployment_app.command("list")
@cli_errors
def deployment_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List deployments (name, namespace, desired/ready/available, age)."""
    conn, _ = get_connection(target)
    rows = workloads.list_deployments(conn, namespace)
    table = Table(title="Deployments")
    for col in ("name", "namespace", "desired", "ready", "available", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], str(r["desired"]),
            str(r["ready"]), str(r["available"]), r["age"],
        )
    console.print(table)


@deployment_app.command("get")
@cli_errors
def deployment_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show detail for one deployment."""
    conn, _ = get_connection(target)
    for k, v in workloads.get_deployment(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@deployment_app.command("scale")
@cli_errors
def deployment_scale(
    name: str,
    replicas: int,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
) -> None:
    """Scale a deployment to a replica count."""
    conn, _ = get_connection(target)
    result = lifecycle.scale_deployment(conn, name, replicas, namespace)
    console.print(
        f"[green]Scaled {name} -> {replicas}[/] "
        f"(was {result['previous_replicas']})"
    )


@deployment_app.command("restart")
@cli_errors
def deployment_restart(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Trigger a rolling restart of a deployment."""
    conn, _ = get_connection(target)
    lifecycle.rollout_restart_deployment(conn, name, namespace)
    console.print(f"[green]Rollout restart triggered for {name}[/]")


@deployment_app.command("delete")
@cli_errors
def deployment_delete(
    name: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Delete a deployment and its pods (HIGH RISK — double confirm)."""
    if dry_run:
        dry_run_print(operation="delete_deployment", detail=f"delete deployment {name}")
        return
    double_confirm("delete", f"deployment {name}")
    conn, _ = get_connection(target)
    lifecycle.delete_deployment(conn, name, namespace)
    console.print(f"[green]Deleted deployment {name}[/]")
