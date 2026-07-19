"""``k8s-aiops configmap ...`` and ``k8s-aiops secret ...`` sub-commands.

SECURITY: ``secret list`` shows names, types, and key NAMES only — never values.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    NamespaceOption,
    TargetOption,
    cli_errors,
    get_connection,
    join_opt,
)
from k8s_aiops.ops import config_resources

configmap_app = typer.Typer(help="ConfigMap operations.", no_args_is_help=True)
secret_app = typer.Typer(help="Secret operations (names/keys only).", no_args_is_help=True)
console = Console()


@configmap_app.command("list")
@cli_errors
def configmap_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List configmaps (name, namespace, key count, age)."""
    conn, _ = get_connection(target)
    rows = config_resources.list_configmaps(conn, namespace)
    table = Table(title="ConfigMaps")
    for col in ("name", "namespace", "keys", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["name"], r["namespace"], str(r["keys"]), r["age"])
    console.print(table)


@configmap_app.command("get")
@cli_errors
def configmap_get(
    name: str, target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Show a configmap's data (keys + values)."""
    conn, _ = get_connection(target)
    result = config_resources.get_configmap(conn, name, namespace)
    console.print(f"  [cyan]name:[/] {result['name']}  [cyan]namespace:[/] {result['namespace']}")
    for k, v in result["data"].items():
        console.print(f"  [cyan]{k}:[/] {v}")


@secret_app.command("list")
@cli_errors
def secret_list(target: TargetOption = None, namespace: NamespaceOption = None) -> None:
    """List secrets — names, types, and key NAMES only (values never shown)."""
    conn, _ = get_connection(target)
    rows = config_resources.list_secrets(conn, namespace)
    table = Table(title="Secrets (values redacted)")
    for col in ("name", "namespace", "type", "key_names", "age"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["name"], r["namespace"], r["type"], join_opt(r["key_names"]), r["age"]
        )
    console.print(table)
