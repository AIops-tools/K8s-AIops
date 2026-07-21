"""``k8s-aiops rollout ...`` sub-commands for deployments."""

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
    join_opt,
)
from k8s_aiops.ops import rollout
from mcp_server.tools import rollout as gov

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
        table.add_row(str(r["revision"]), r["replicaset"], join_opt(r["images"]))
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
        preview = gov.rollout_undo_deployment(
            name=name, namespace=namespace, to_revision=to_revision, target=target,
            dry_run=True,
        )
        dry_run_preview(
            preview,
            operation="rollout_undo",
            detail=f"roll back {name}",
            parameters=preview.get("wouldRollBack"),
        )
        return
    double_confirm("roll back", f"deployment {name}")
    console.print_json(
        json.dumps(
            gov.rollout_undo_deployment(
                name=name, namespace=namespace, to_revision=to_revision, target=target
            )
        )
    )


@rollout_app.command("pause")
@cli_errors
def rollout_pause(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Pause a deployment's rollout."""
    console.print_json(
        json.dumps(gov.rollout_pause(name=name, namespace=namespace, target=target))
    )


@rollout_app.command("resume")
@cli_errors
def rollout_resume(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Resume a paused deployment's rollout."""
    console.print_json(
        json.dumps(gov.rollout_resume(name=name, namespace=namespace, target=target))
    )


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
    console.print_json(
        json.dumps(
            gov.set_deployment_image(
                name=name,
                container=container,
                image=image,
                namespace=namespace,
                target=target,
            )
        )
    )
