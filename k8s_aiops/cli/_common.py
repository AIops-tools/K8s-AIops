"""Shared helpers for k8s-aiops CLI sub-modules."""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

console = Console()

# ─── Shared Option types ───────────────────────────────────────────────────

TargetOption = Annotated[
    str | None, typer.Option("--target", "-t", help="Target name from config")
]
NamespaceOption = Annotated[
    str | None, typer.Option("--namespace", "-n", help="Namespace (omit for all/default)")
]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", help="Print the operation without executing")
]


def _cli_error_types() -> tuple[type[BaseException], ...]:
    """Exceptions translated to a one-line teaching error instead of a traceback."""
    from k8s_aiops.connection import K8sApiError

    return (K8sApiError, KeyError, OSError, ValueError)


def cli_errors(fn: Callable) -> Callable:
    """Translate known exceptions into one red line + exit code 1."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except _cli_error_types() as e:
            message = str(e)
            if isinstance(e, KeyError):
                message = f"Missing required key: {message}"
            console.print(f"[red]Error: {message}[/]")
            raise typer.Exit(1) from e

    return wrapper


def get_connection(target: str | None, config_path: Path | None = None) -> tuple[Any, Any]:
    """Return a (conn, config) tuple for the given target."""
    from k8s_aiops.config import load_config
    from k8s_aiops.connection import ConnectionManager

    cfg = load_config(config_path)
    mgr = ConnectionManager(cfg)
    return mgr.connect(target), cfg


def get_target_config(target: str | None, config_path: Path | None = None) -> Any:
    """Resolve a target's config without building an API client.

    Write guards need it on the ``--dry-run`` path, which prints a preview
    without ever connecting — a preview may read, but must never write.
    """
    from k8s_aiops.config import load_config
    from k8s_aiops.connection import ConnectionManager

    return ConnectionManager(load_config(config_path)).target_config(target)


def dry_run_print(*, operation: str, detail: str, parameters: dict | None = None) -> None:
    """Print a dry-run preview of the operation that would be performed."""
    console.print("\n[bold magenta][DRY-RUN] No changes will be made.[/]")
    console.print(f"[magenta]  Operation: {operation}[/]")
    console.print(f"[magenta]  Detail:    {detail}[/]")
    for k, v in (parameters or {}).items():
        console.print(f"[magenta]  Param:     {k} = {v}[/]")
    console.print("[magenta]  Run without --dry-run to execute.[/]\n")


def double_confirm(action: str, resource: str) -> None:
    """Require two confirmations for a destructive operation."""
    console.print(f"[bold yellow]⚠️  About to: {action} '{resource}'[/]")
    typer.confirm(f"Confirm 1/2: {action} '{resource}'?", abort=True)
    typer.confirm(
        f"Confirm 2/2: really {action} '{resource}'? This may be irreversible.",
        abort=True,
    )


def join_opt(values: list[str | None] | None, sep: str = ",") -> str:
    """Join a list whose elements may be ``None`` into a table cell.

    Ops rows report an absent field as ``None`` rather than ``""``. A list
    element can therefore be ``None`` too, and ``str.join`` raises on it. A
    missing element is rendered as ``?`` so it stays visible instead of being
    silently dropped.
    """
    return sep.join("?" if v is None else str(v) for v in (values or []))
