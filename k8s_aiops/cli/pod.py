"""``k8s-aiops pod ...`` sub-commands."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    DryRunOption,
    NamespaceOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_preview,
    get_connection,
)
from k8s_aiops.ops import describe, workloads
from mcp_server.tools import lifecycle as gov

pod_app = typer.Typer(help="Pod operations.", no_args_is_help=True)
console = Console()


@pod_app.command("list")
@cli_errors
def pod_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List pods (name, namespace, phase, ready, restarts, node, age)."""
    conn, _ = get_connection(target)
    rows = workloads.list_pods(conn, namespace)
    table = Table(title="Pods")
    for col in ("name", "namespace", "phase", "ready", "restarts", "node", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], r["phase"], r["ready"],
            str(r["restarts"]), r["node"], r["age"],
        )
    console.print(table)


@pod_app.command("get")
@cli_errors
def pod_get(name: str, target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """Show detail for one pod."""
    conn, _ = get_connection(target)
    for k, v in workloads.get_pod(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@pod_app.command("describe")
@cli_errors
def pod_describe(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Describe a pod: status, conditions, container states, recent events."""
    conn, _ = get_connection(target)
    result = describe.pod_describe(conn, name, namespace)
    for k in ("name", "namespace", "phase", "node", "pod_ip"):
        console.print(f"  [cyan]{k}:[/] {result[k]}")
    console.print("  [cyan]containers:[/]")
    for c in result["containers"]:
        console.print(
            f"    - {c['name']} ready={c['ready']} restarts={c['restarts']} "
            f"state={c['state']}"
        )
    console.print("  [cyan]events:[/]")
    for e in result["events"]:
        console.print(f"    - {e['type']} {e['reason']}: {e['message']} ({e['age']})")


@pod_app.command("logs")
@cli_errors
def pod_logs(
    name: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    tail: int = typer.Option(100, "--tail", help="Number of trailing log lines"),
    container: str = typer.Option(None, "--container", "-c", help="Container name"),
) -> None:
    """Show recent log lines for a pod."""
    conn, _ = get_connection(target)
    result = workloads.get_pod_logs(conn, name, namespace, tail, container)
    console.print(result["logs"])


@pod_app.command("delete")
@cli_errors
def pod_delete(
    name: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Delete a pod (destructive — double confirm). A controller may recreate it."""
    if dry_run:
        preview = gov.delete_pod(name=name, namespace=namespace, target=target, dry_run=True)
        dry_run_preview(
            preview,
            operation="delete_pod",
            detail=f"delete pod {name}",
            parameters=preview.get("wouldDelete"),
        )
        return
    double_confirm("delete", f"pod {name}")
    console.print_json(
        json.dumps(gov.delete_pod(name=name, namespace=namespace, target=target))
    )
