"""``k8s-aiops namespace ...`` sub-commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    DryRunOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_preview,
    get_connection,
    get_target_config,
)
from k8s_aiops.ops import namespaces
from mcp_server.tools import namespaces as gov

namespace_app = typer.Typer(help="Namespace operations.", no_args_is_help=True)
console = Console()

ConfirmProtectedOption = Annotated[
    bool,
    typer.Option(
        "--confirm",
        help="Allow deleting a protected control-plane namespace (kube-system etc.)",
    ),
]


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
    name: str,
    target: TargetOption = None,
    dry_run: DryRunOption = False,
    confirm: ConfirmProtectedOption = False,
) -> None:
    """Delete a namespace and EVERYTHING in it (HIGH RISK — double confirm)."""
    if dry_run:
        # Through the governed twin: it runs the protected/self-lockout guards
        # itself, so a preview reports the refusal the real delete would raise
        # instead of a green banner — and the refusal is audited like any other
        # governed outcome.
        preview = gov.delete_namespace(
            name=name, target=target, confirm=confirm, dry_run=True
        )
        dry_run_preview(
            preview,
            operation="delete_namespace",
            detail=f"delete namespace {name} and everything in it",
            parameters=preview.get("wouldDelete"),
        )
        return
    # Ahead of the prompts on the real path: nobody should be asked to
    # double-confirm a delete the guard is about to refuse anyway.
    namespaces.guard_delete_namespace(
        name, confirm=confirm, target=get_target_config(target)
    )
    double_confirm("delete", f"namespace {name} (and all its resources)")
    console.print_json(
        json.dumps(gov.delete_namespace(name=name, target=target, confirm=confirm))
    )
