"""``k8s-aiops daemonset ...`` sub-commands."""

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

daemonset_app = typer.Typer(help="DaemonSet operations.", no_args_is_help=True)
console = Console()


@daemonset_app.command("list")
@cli_errors
def daemonset_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List daemonsets (name, namespace, desired/ready/available, age)."""
    conn, _ = get_connection(target)
    rows = controllers.list_daemonsets(conn, namespace)
    table = Table(title="DaemonSets")
    for col in ("name", "namespace", "desired", "ready", "available", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], str(r["desired"]),
            str(r["ready"]), str(r["available"]), r["age"],
        )
    console.print(table)


@daemonset_app.command("get")
@cli_errors
def daemonset_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show detail for one daemonset."""
    conn, _ = get_connection(target)
    for k, v in controllers.get_daemonset(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")
