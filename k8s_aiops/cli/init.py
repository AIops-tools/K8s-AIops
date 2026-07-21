"""``k8s-aiops init`` — a friendly, interactive onboarding wizard.

Kubernetes credentials live in the kubeconfig, so there is no secret store to
seed. This wizard discovers the contexts in your kubeconfig, lets you register
one or more as named targets (each with an optional default namespace), and
writes ``~/.k8s-aiops/config.yaml`` (dir chmod 700), merging with any existing
targets. It then offers to run ``k8s-aiops doctor``.
"""

from __future__ import annotations

from typing import Any

import typer
import yaml

from k8s_aiops.cli._common import cli_errors, console
from k8s_aiops.config import CONFIG_DIR, CONFIG_FILE


def _list_contexts() -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return (contexts, active_context) from the kubeconfig.

    Raises a friendly RuntimeError when no kubeconfig is available.
    """
    from kubernetes import config as k8s_config
    from kubernetes.config.config_exception import ConfigException

    try:
        contexts, active = k8s_config.list_kube_config_contexts()
    except ConfigException as exc:
        raise RuntimeError(
            "No kubeconfig found. Point KUBECONFIG at your config or place it at "
            f"~/.kube/config, then re-run 'k8s-aiops init'. (detail: {exc})"
        ) from exc
    return list(contexts or []), active


def _load_existing_targets() -> list[dict]:
    if not CONFIG_FILE.exists():
        return []
    raw = yaml.safe_load(CONFIG_FILE.read_text("utf-8")) or {}
    return list(raw.get("targets", []))


def _write_targets(targets: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    CONFIG_FILE.write_text(yaml.safe_dump({"targets": targets}, sort_keys=False), "utf-8")


def _print_contexts(contexts: list[dict], active_name: str) -> None:
    console.print("\n[bold]Available kube contexts:[/]")
    for i, ctx in enumerate(contexts, start=1):
        name = ctx.get("name", "")
        marker = " [green](current)[/]" if name == active_name else ""
        console.print(f"  [cyan]{i}[/]. {name}{marker}")


def _select_context(contexts: list[dict], active_name: str) -> dict:
    """Prompt the user to pick one context by number (default: current)."""
    default_idx = next(
        (i for i, c in enumerate(contexts, start=1) if c.get("name") == active_name), 1
    )
    while True:
        choice = typer.prompt("Pick a context number to register", default=default_idx, type=int)
        if 1 <= choice <= len(contexts):
            return contexts[choice - 1]
        console.print(f"[yellow]Enter a number between 1 and {len(contexts)}.[/]")


def _add_target(targets: list[dict], existing: set[str], ctx: dict) -> bool:
    """Prompt for a target name/namespace for ``ctx``; append to ``targets``.

    Returns False if the user declined to overwrite an existing name.
    """
    ctx_name = ctx.get("name", "")
    name = typer.prompt("Target name", default=ctx_name).strip()
    if name in existing:
        if not typer.confirm(f"'{name}' already exists — overwrite?", default=False):
            return False
        targets[:] = [t for t in targets if t.get("name") != name]
        existing.discard(name)
    ctx_default_ns = (ctx.get("context") or {}).get("namespace", "")
    namespace = typer.prompt(
        "Default namespace (Enter to skip)", default=ctx_default_ns or ""
    ).strip()
    entry: dict[str, Any] = {"name": name, "context": ctx_name}
    if namespace:
        entry["namespace"] = namespace
    targets.append(entry)
    existing.add(name)
    return True


@cli_errors
def init_cmd() -> None:
    """Interactively register kube contexts as k8s-aiops targets."""
    console.print("[bold cyan]k8s AIops — setup wizard[/]")
    console.print(
        "This registers kube contexts as named targets in config.yaml. "
        "Credentials stay in your kubeconfig — nothing secret is stored here.\n"
    )

    contexts, active = _list_contexts()
    if not contexts:
        console.print(
            "[yellow]Your kubeconfig has no contexts. Add one (e.g. "
            "'kubectl config set-context ...') and re-run 'k8s-aiops init'.[/]"
        )
        raise typer.Exit(1)
    active_name = (active or {}).get("name", "")

    targets = _load_existing_targets()
    existing = {t.get("name") for t in targets if t.get("name")}

    while True:
        _print_contexts(contexts, active_name)
        ctx = _select_context(contexts, active_name)
        if _add_target(targets, existing, ctx):
            _write_targets(targets)
            console.print(f"[green]✓ Saved target for context '{ctx.get('name')}'.[/]")
        if not typer.confirm("\nRegister another context?", default=False):
            break

    console.print(f"\n[green]✓ Setup complete.[/] Config: {CONFIG_FILE}")
    if typer.confirm("Run a connectivity check now (k8s-aiops doctor)?", default=True):
        from k8s_aiops.doctor import run_doctor

        raise typer.Exit(run_doctor())
