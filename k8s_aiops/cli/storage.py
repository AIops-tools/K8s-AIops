"""``k8s-aiops storage ...`` sub-commands: pvc, pv, storageclass."""

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
from k8s_aiops.ops import storage

storage_app = typer.Typer(help="Storage operations (pvc, pv, storageclass).", no_args_is_help=True)
console = Console()


@storage_app.command("pvc-list")
@cli_errors
def pvc_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List persistent volume claims."""
    conn, _ = get_connection(target)
    rows = storage.list_pvcs(conn, namespace)
    table = Table(title="PersistentVolumeClaims")
    for col in ("name", "namespace", "status", "volume", "capacity", "storage_class", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], r["status"], r["volume"],
            r["capacity"], r["storage_class"], r["age"],
        )
    console.print(table)


@storage_app.command("pvc-get")
@cli_errors
def pvc_get(name: str, target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """Show detail for one PVC."""
    conn, _ = get_connection(target)
    for k, v in storage.get_pvc(conn, name, namespace).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@storage_app.command("pv-list")
@cli_errors
def pv_list(target: TargetOption = None) -> None:
    """List persistent volumes."""
    conn, _ = get_connection(target)
    rows = storage.list_pvs(conn)
    table = Table(title="PersistentVolumes")
    for col in ("name", "capacity", "status", "claim", "storage_class", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["capacity"], r["status"], r["claim"], r["storage_class"], r["age"]
        )
    console.print(table)


@storage_app.command("class-list")
@cli_errors
def storageclass_list(target: TargetOption = None) -> None:
    """List storage classes."""
    conn, _ = get_connection(target)
    rows = storage.list_storageclasses(conn)
    table = Table(title="StorageClasses")
    for col in ("name", "provisioner", "reclaim_policy", "volume_binding_mode", "default"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["provisioner"], r["reclaim_policy"],
            r["volume_binding_mode"], str(r["default"]),
        )
    console.print(table)
