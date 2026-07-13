"""Environment and connectivity diagnostics for k8s-aiops."""

from __future__ import annotations

from rich.console import Console

from k8s_aiops.config import CONFIG_FILE, load_config

_console = Console()


def _kubeconfig_context_names() -> set[str] | None:
    """Return the set of context names in the kubeconfig, or None if unavailable.

    Never raises — a missing/broken kubeconfig is a reported status, not a crash.
    """
    try:
        from kubernetes import config as k8s_config

        contexts, _ = k8s_config.list_kube_config_contexts()
        return {c.get("name", "") for c in (contexts or [])}
    except Exception:  # noqa: BLE001 — kubeconfig issues are a status, not a crash
        return None


def _check_contexts(config: object) -> int:
    """Verify each target's context exists in the kubeconfig. Returns # problems."""
    names = _kubeconfig_context_names()
    if names is None:
        _console.print(
            "[yellow]! Could not read kubeconfig contexts (KUBECONFIG / "
            "~/.kube/config). Connectivity check will reveal if access works.[/]"
        )
        return 0
    problems = 0
    for target in getattr(config, "targets", ()):  # type: ignore[attr-defined]
        ctx = getattr(target, "context", None)
        if not ctx:
            continue  # uses current-context — fine
        if ctx in names:
            _console.print(f"[green]✓ Context '{ctx}' found for target '{target.name}'[/]")
        else:
            _console.print(
                f"[red]✗ Target '{target.name}' references context '{ctx}' which is "
                f"not in the kubeconfig. Run 'kubectl config get-contexts'.[/]"
            )
            problems += 1
    return problems


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
        _console.print(
            "[dim]  Tip: run 'k8s-aiops init' to register your kube contexts as "
            "named targets.[/]"
        )

    try:
        config = load_config()
    except Exception as exc:  # noqa: BLE001 — report, do not crash
        _console.print(f"[red]✗ Config load failed: {exc}[/]")
        return 1
    _console.print(f"[green]✓ {len(config.targets)} target(s) configured[/]")

    problems += _check_contexts(config)

    if skip_auth:
        _console.print("[dim]Skipping connectivity check (--skip-auth).[/]")
        return 1 if problems else 0

    from k8s_aiops.connection import ConnectionManager

    mgr = ConnectionManager(config)
    for target in config.targets:
        try:
            from k8s_aiops.ops._shared import _REQUEST_TIMEOUT

            conn = mgr.connect(target.name)
            ver = conn.version.get_code(_request_timeout=_REQUEST_TIMEOUT)
            _console.print(
                f"[green]✓ Reachable '{target.name}' "
                f"(server {ver.git_version})[/]"
            )
        except Exception as exc:  # noqa: BLE001 — connectivity is a status, not a crash
            _console.print(f"[red]✗ Connect to '{target.name}' failed: {exc}[/]")
            problems += 1

    return 1 if problems else 0
