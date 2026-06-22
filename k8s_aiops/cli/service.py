"""``k8s-aiops service ...`` sub-commands."""

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
from k8s_aiops.ops import workloads

service_app = typer.Typer(help="Service operations.", no_args_is_help=True)
console = Console()


@service_app.command("list")
@cli_errors
def service_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List services (name, namespace, type, cluster IP, ports)."""
    conn, _ = get_connection(target)
    rows = workloads.list_services(conn, namespace)
    table = Table(title="Services")
    for col in ("name", "namespace", "type", "cluster_ip", "ports"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["name"], r["namespace"], r["type"], r["cluster_ip"], r["ports"])
    console.print(table)
