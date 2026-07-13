"""``k8s-aiops node ...`` sub-commands."""

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
from k8s_aiops.ops import describe, nodes
from mcp_server.tools import nodes as gov

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


@node_app.command("describe")
@cli_errors
def node_describe(name: str, target: TargetOption = None) -> None:
    """Describe a node: capacity, allocatable, conditions, taints."""
    conn, _ = get_connection(target)
    result = describe.node_describe(conn, name)
    for k in ("name", "schedulable", "age"):
        console.print(f"  [cyan]{k}:[/] {result[k]}")
    console.print(f"  [cyan]capacity:[/] {result['capacity']}")
    console.print(f"  [cyan]allocatable:[/] {result['allocatable']}")
    console.print(f"  [cyan]taints:[/] {result['taints']}")
    console.print("  [cyan]conditions:[/]")
    for c in result["conditions"]:
        console.print(f"    - {c['type']}={c['status']} {c['reason']}")


@node_app.command("drain")
@cli_errors
def node_drain(
    name: str, target: TargetOption = None, dry_run: DryRunOption = False
) -> None:
    """Cordon a node and evict its pods (HIGH RISK — double confirm)."""
    if dry_run:
        dry_run_print(operation="drain_node", detail=f"cordon + evict pods on {name}")
        return
    double_confirm("drain", f"node {name}")
    console.print_json(json.dumps(gov.drain_node(name=name, target=target)))


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
    console.print_json(json.dumps(gov.cordon_node(name=name, target=target)))


@node_app.command("uncordon")
@cli_errors
def node_uncordon(name: str, target: TargetOption = None) -> None:
    """Mark a node schedulable again."""
    console.print_json(json.dumps(gov.uncordon_node(name=name, target=target)))
