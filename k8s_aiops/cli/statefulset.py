"""``k8s-aiops statefulset ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    NamespaceOption,
    TargetOption,
    cli_errors,
    get_connection,
)
from k8s_aiops.ops import controllers

statefulset_app = typer.Typer(help="StatefulSet operations.", no_args_is_help=True)
console = Console()


@statefulset_app.command("list")
@cli_errors
def statefulset_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List statefulsets (name, namespace, desired/ready/current, age)."""
    conn, _ = get_connection(target)
    rows = controllers.list_statefulsets(conn, namespace)
    table = Table(title="StatefulSets")
    for col in ("name", "namespace", "desired", "ready", "current", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], str(r["desired"]),
            str(r["ready"]), str(r["current"]), r["age"],
        )
    console.print(table)


@statefulset_app.command("get")
@cli_errors
def statefulset_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show detail for one statefulset."""
    conn, _ = get_connection(target)
    for k, v in controllers.get_statefulset(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@statefulset_app.command("scale")
@cli_errors
def statefulset_scale(
    name: str,
    replicas: int,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
) -> None:
    """Scale a statefulset to a replica count."""
    conn, _ = get_connection(target)
    result = controllers.scale_statefulset(conn, name, replicas, namespace)
    console.print(
        f"[green]Scaled {name} -> {replicas}[/] (was {result['previous_replicas']})"
    )
