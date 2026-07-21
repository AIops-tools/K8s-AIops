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
    """Exceptions translated to a one-line teaching error instead of a traceback.

    ``PolicyDenied`` is kept here defensively even though the harness no longer
    raises it (there is no read-only switch or approval gate to deny a call): it
    is raised OUTSIDE ``@tool_errors`` (``@governed_tool`` wraps it), so it never
    becomes an ``{"error": ...}`` dict the dry-run helper could catch. Were it
    ever raised, listing it keeps the user from getting a bare traceback.
    """
    from k8s_aiops.connection import K8sApiError
    from k8s_aiops.governance import PolicyDenied

    return (K8sApiError, KeyError, OSError, ValueError, PolicyDenied)


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

    A write guard needs it before the confirm prompts, so an operator is never
    asked to double-confirm a delete the guard is about to refuse.
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


def dry_run_preview(
    preview: Any, *, operation: str, detail: str, parameters: dict | None = None
) -> None:
    """Render a GOVERNED dry-run result as the human-readable DRY-RUN banner.

    ``preview`` must come from calling the governed twin with ``dry_run=True``,
    so every guard it carries has already run against the real target and the
    preview lands in the audit log — MCP previews have always been audited, the
    CLI printing a hand-written string was the outlier.

    A refusal arrives as ``{"error": ...}`` (``tool_errors`` flattens the
    exception) and is printed like any other CLI error, exit code 1, exactly as
    the real write would. A green banner for a call that is about to be refused
    is the preview being wrong, not merely incomplete.

    On the allowed path the banner is what it always was — routing through the
    governed call buys the guard and the audit row, not a new serialization.

    Invariant: **a dry_run MAY read; it must never write.**
    """
    if isinstance(preview, dict) and preview.get("error"):
        console.print(f"[red]Error: {preview['error']}[/]")
        raise typer.Exit(1)
    dry_run_print(operation=operation, detail=detail, parameters=parameters)


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
