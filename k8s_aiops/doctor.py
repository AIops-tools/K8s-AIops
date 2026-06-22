"""Environment and connectivity diagnostics for k8s-aiops."""

from __future__ import annotations

from rich.console import Console

from k8s_aiops.config import CONFIG_FILE, load_config

_console = Console()


def run_doctor(skip_auth: bool = False) -> int:
    """Check config and (optionally) cluster reachability.

    Returns a process exit code: 0 healthy, 1 problems found. Connectivity
    failures are reported as status, never raised as tracebacks (a doctor must
    survive the thing it diagnoses being unhealthy).
    """
    problems = 0

    if CONFIG_FILE.exists():
        _console.print(f"[green]✓ Config file present: {CONFIG_FILE}[/]")
    else:
        _console.print(
            f"[yellow]! No config file ({CONFIG_FILE}); using current kube-context.[/]"
        )

    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001 — report, do not crash
        _console.print(f"[red]✗ Config load failed: {exc}[/]")
        return 1
    _console.print(f"[green]✓ {len(config.targets)} target(s) configured[/]")

    if skip_auth:
        _console.print("[dim]Skipping connectivity check (--skip-auth).[/]")
        return 1 if problems else 0

    from k8s_aiops.connection import ConnectionManager

    mgr = ConnectionManager(config)
    for target in config.targets:
        try:
            conn = mgr.connect(target.name)
            ver = conn.version.get_code()
            _console.print(
                f"[green]✓ Reachable '{target.name}' "
                f"(server {ver.git_version})[/]"
            )
        except Exception as exc:  # noqa: BLE001 — connectivity is a status, not a crash
            _console.print(f"[red]✗ Connect to '{target.name}' failed: {exc}[/]")
            problems += 1

    return 1 if problems else 0
