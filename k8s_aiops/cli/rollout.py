"""``k8s-aiops rollout ...`` sub-commands for deployments."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    DryRunOption,
    NamespaceOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_print,
    get_connection,
)
from k8s_aiops.ops import rollout

rollout_app = typer.Typer(help="Deployment rollout operations.", no_args_is_help=True)
console = Console()


@rollout_app.command("status")
@cli_errors
def rollout_status(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show rollout status for a deployment."""
    conn, _ = get_connection(target)
    for k, v in rollout.rollout_status(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@rollout_app.command("history")
@cli_errors
def rollout_history(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """List a deployment's rollout revisions."""
    conn, _ = get_connection(target)
    rows = rollout.rollout_history(conn, name, namespace)
    table = Table(title=f"Rollout history: {name}")
    for col in ("revision", "replicaset", "images"):
        table.add_column(col)
    for r in rows:
        table.add_row(str(r["revision"]), r["replicaset"], ",".join(r["images"]))
    console.print(table)


@rollout_app.command("undo")
@cli_errors
def rollout_undo(
    name: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    to_revision: int = typer.Option(0, "--to-revision", help="Revision (0 = previous)"),
    dry_run: DryRunOption = False,
) -> None:
    """Roll a deployment back to a prior revision (HIGH RISK — double confirm)."""
    if dry_run:
        dry_run_print(operation="rollout_undo", detail=f"roll back {name}",
                      parameters={"to_revision": to_revision or "previous"})
        return
    double_confirm("roll back", f"deployment {name}")
    conn, _ = get_connection(target)
    result = rollout.rollout_undo(conn, name, namespace, to_revision)
    console.print(
        f"[green]Rolled {name} back to revision {result['rolled_to_revision']}[/] "
        f"(from {result['from_revision']})"
    )


@rollout_app.command("pause")
@cli_errors
def rollout_pause(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Pause a deployment's rollout."""
    conn, _ = get_connection(target)
    rollout.rollout_pause(conn, name, namespace)
    console.print(f"[green]Paused rollout of {name}[/]")


@rollout_app.command("resume")
@cli_errors
def rollout_resume(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Resume a paused deployment's rollout."""
    conn, _ = get_connection(target)
    rollout.rollout_resume(conn, name, namespace)
    console.print(f"[green]Resumed rollout of {name}[/]")


@rollout_app.command("set-image")
@cli_errors
def rollout_set_image(
    name: str,
    container: str,
    image: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
) -> None:
    """Update a deployment container's image."""
    conn, _ = get_connection(target)
    result = rollout.set_deployment_image(conn, name, container, image, namespace)
    console.print(
        f"[green]Set {name}/{container} image -> {image}[/] "
        f"(was {result['previous_image']})"
    )
