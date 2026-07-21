"""``k8s-aiops job ...`` and ``k8s-aiops cronjob ...`` sub-commands."""

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
from k8s_aiops.ops import batch
from mcp_server.tools import batch as gov

job_app = typer.Typer(help="Job operations.", no_args_is_help=True)
cronjob_app = typer.Typer(help="CronJob operations.", no_args_is_help=True)
console = Console()


@job_app.command("list")
@cli_errors
def job_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List jobs (name, namespace, completions, succeeded/failed, age)."""
    conn, _ = get_connection(target)
    rows = batch.list_jobs(conn, namespace)
    table = Table(title="Jobs")
    for col in ("name", "namespace", "completions", "succeeded", "failed", "active", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], str(r["completions"]), str(r["succeeded"]),
            str(r["failed"]), str(r["active"]), r["age"],
        )
    console.print(table)


@job_app.command("get")
@cli_errors
def job_get(name: str, target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """Show detail for one job."""
    conn, _ = get_connection(target)
    for k, v in batch.get_job(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@job_app.command("delete")
@cli_errors
def job_delete(
    name: str,
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Delete a job and its pods (destructive — double confirm)."""
    if dry_run:
        preview = gov.delete_job(name=name, namespace=namespace, target=target, dry_run=True)
        dry_run_preview(
            preview,
            operation="delete_job",
            detail=f"delete job {name}",
            parameters=preview.get("wouldDelete"),
        )
        return
    double_confirm("delete", f"job {name}")
    console.print_json(
        json.dumps(gov.delete_job(name=name, namespace=namespace, target=target))
    )


@cronjob_app.command("list")
@cli_errors
def cronjob_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List cronjobs (name, namespace, schedule, suspend, active, age)."""
    conn, _ = get_connection(target)
    rows = batch.list_cronjobs(conn, namespace)
    table = Table(title="CronJobs")
    for col in ("name", "namespace", "schedule", "suspend", "active", "last_schedule", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], r["schedule"], str(r["suspend"]),
            str(r["active"]), r["last_schedule"], r["age"],
        )
    console.print(table)


@cronjob_app.command("get")
@cli_errors
def cronjob_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show detail for one cronjob."""
    conn, _ = get_connection(target)
    for k, v in batch.get_cronjob(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")
