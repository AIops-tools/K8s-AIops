"""``k8s-aiops top ...`` sub-commands (resource usage via metrics-server)."""

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
from k8s_aiops.ops import metrics

top_app = typer.Typer(help="Resource usage (requires metrics-server).", no_args_is_help=True)
console = Console()


@top_app.command("node")
@cli_errors
def top_node(target: TargetOption = None) -> None:
    """CPU/memory usage per node."""
    conn, _ = get_connection(target)
    result = metrics.node_top(conn)
    if not result.get("available"):
        console.print(f"[yellow]{result['message']}[/]")
        return
    table = Table(title="Node usage")
    for col in ("name", "cpu", "memory"):
        table.add_column(col)
    for r in result["items"]:
        table.add_row(r["name"], r["cpu"], r["memory"])
    console.print(table)


@top_app.command("pod")
@cli_errors
def top_pod(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """CPU/memory usage per pod."""
    conn, _ = get_connection(target)
    result = metrics.pod_top(conn, namespace)
    if not result.get("available"):
        console.print(f"[yellow]{result['message']}[/]")
        return
    table = Table(title="Pod usage")
    for col in ("namespace", "pod", "container", "cpu", "memory"):
        table.add_column(col)
    for r in result["items"]:
        for c in r["containers"]:
            table.add_row(r["namespace"], r["name"], c["name"], c["cpu"], c["memory"])
    console.print(table)
