"""``k8s-aiops node ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    DryRunOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_print,
    get_connection,
)
from k8s_aiops.ops import lifecycle, nodes

node_app = typer.Typer(help="Node operations.", no_args_is_help=True)
console = Console()


@node_app.command("list")
@cli_errors
def node_list(target: TargetOption = None) -> None:
    """List nodes (name, status, roles, version, schedulable, age)."""
    conn, _ = get_connection(target)
    rows = nodes.list_nodes(conn)
    table = Table(title="Nodes")
    for col in ("name", "status", "roles", "version", "schedulable", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["status"], r["roles"], r["version"],
            str(r["schedulable"]), r["age"],
        )
    console.print(table)


@node_app.command("cordon")
@cli_errors
def node_cordon(
    name: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Mark a node unschedulable (destructive — double confirm)."""
    if dry_run:
        dry_run_print(operation="cordon_node", detail=f"cordon node {name}")
        return
    double_confirm("cordon", f"node {name}")
    conn, _ = get_connection(target)
    lifecycle.cordon_node(conn, name)
    console.print(f"[green]Cordoned node {name}[/]")


@node_app.command("uncordon")
@cli_errors
def node_uncordon(name: str, target: TargetOption = None) -> None:
    """Mark a node schedulable again."""
    conn, _ = get_connection(target)
    lifecycle.uncordon_node(conn, name)
    console.print(f"[green]Uncordoned node {name}[/]")
