"""``k8s-aiops namespace ...`` sub-commands."""

from __future__ import annotations

import json

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
from k8s_aiops.ops import namespaces
from mcp_server.tools import namespaces as gov

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


@namespace_app.command("create")
@cli_errors
def namespace_create(name: str, target: TargetOption = None) -> None:
    """Create a namespace."""
    console.print_json(json.dumps(gov.create_namespace(name=name, target=target)))


@namespace_app.command("delete")
@cli_errors
def namespace_delete(
    name: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Delete a namespace and EVERYTHING in it (HIGH RISK — double confirm)."""
    if dry_run:
        dry_run_print(operation="delete_namespace", detail=f"delete namespace {name}")
        return
    double_confirm("delete", f"namespace {name} (and all its resources)")
    console.print_json(json.dumps(gov.delete_namespace(name=name, target=target)))
