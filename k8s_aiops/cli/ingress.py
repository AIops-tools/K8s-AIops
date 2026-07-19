"""``k8s-aiops ingress ...`` and ``k8s-aiops endpoints`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    NamespaceOption,
    TargetOption,
    cli_errors,
    get_connection,
    join_opt,
)
from k8s_aiops.ops import networking

ingress_app = typer.Typer(help="Ingress operations.", no_args_is_help=True)
console = Console()


@ingress_app.command("list")
@cli_errors
def ingress_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List ingresses (name, namespace, class, hosts, age)."""
    conn, _ = get_connection(target)
    rows = networking.list_ingresses(conn, namespace)
    table = Table(title="Ingresses")
    for col in ("name", "namespace", "class", "hosts", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["name"], r["namespace"], r["class"], join_opt(r["hosts"]), r["age"])
    console.print(table)


@ingress_app.command("get")
@cli_errors
def ingress_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show detail for one ingress (host/path → backend service)."""
    conn, _ = get_connection(target)
    result = networking.get_ingress(conn, name, namespace)
    console.print(f"  [cyan]name:[/] {result['name']}  [cyan]class:[/] {result['class']}")
    for p in result["paths"]:
        console.print(
            f"  [cyan]{p['host']}{p['path']}[/] -> {p['service']}:{p['port']}"
        )
