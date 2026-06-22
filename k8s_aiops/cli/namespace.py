"""``k8s-aiops namespace ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import TargetOption, cli_errors, get_connection
from k8s_aiops.ops import namespaces

namespace_app = typer.Typer(help="Namespace operations.", no_args_is_help=True)
console = Console()


@namespace_app.command("list")
@cli_errors
def namespace_list(target: TargetOption = None) -> None:
    """List namespaces (name, phase, age)."""
    conn, _ = get_connection(target)
    rows = namespaces.list_namespaces(conn)
    table = Table(title="Namespaces")
    for col in ("name", "phase", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["name"], r["phase"], r["age"])
    console.print(table)
