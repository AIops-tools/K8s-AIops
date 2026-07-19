"""``k8s-aiops diagnose ...`` sub-commands — read-only RCA over the cluster."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import NamespaceOption, TargetOption, cli_errors, get_connection
from k8s_aiops.ops import diagnostics as diag
from mcp_server.tools import diagnostics as gov

diagnose_app = typer.Typer(
    help="Read-only diagnostics / RCA over the cluster.", no_args_is_help=True
)
console = Console()

_SEVERITY_STYLE = {"critical": "red", "warning": "yellow", "info": "cyan"}


def _print_findings(findings: list[dict]) -> None:
    """Render worst-first findings as a table, or a green all-clear line."""
    if not findings:
        console.print("[green]No findings — all scanned objects are healthy.[/]")
        return
    table = Table(title="Findings (worst first)")
    for col in ("severity", "target", "signal", "detail", "action"):
        table.add_column(col, overflow="fold")
    for f in findings:
        style = _SEVERITY_STYLE.get(f["severity"], "white")
        table.add_row(
            f"[{style}]{f['severity']}[/]", f.get("target", ""),
            f["signal"], f["detail"], f["action"],
        )
    console.print(table)


@diagnose_app.command("pod-health")
@cli_errors
def diagnose_pod_health(
    target: TargetOption = None,
    namespace: NamespaceOption = None,
    label_selector: str = typer.Option(None, "--selector", "-l", help="Label selector"),
) -> None:
    """Flag CrashLoopBackOff, image-pull failures, OOMKilled, unschedulable, high restarts."""
    conn, _ = get_connection(target)
    rows = gov.collect_pod_rows(conn, namespace, label_selector)
    result = diag.pod_health_findings(rows)
    console.print(f"[bold]Analyzed {result['podsAnalyzed']} pod(s).[/]")
    _print_findings(result["findings"])


@diagnose_app.command("workload-readiness")
@cli_errors
def diagnose_workload_readiness(
    target: TargetOption = None, namespace: NamespaceOption = None
) -> None:
    """Flag Deployments/StatefulSets/DaemonSets with ready<desired or stuck rollouts."""
    conn, _ = get_connection(target)
    rows = gov.collect_workload_rows(conn, namespace)
    result = diag.workload_readiness_findings(rows)
    console.print(f"[bold]Analyzed {result['workloadsAnalyzed']} workload(s).[/]")
    _print_findings(result["findings"])
