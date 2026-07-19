"""``k8s-aiops cluster-info`` and ``k8s-aiops api-resources`` top-level commands."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from k8s_aiops.cli._common import (
    TargetOption,
    cli_errors,
    get_connection,
    join_opt,
)
from k8s_aiops.ops import cluster

console = Console()


@cli_errors
def cluster_info_cmd(target: TargetOption = None) -> None:
    """Show a friendly cluster health summary (version, node/ns counts)."""
    conn, _ = get_connection(target)
    for k, v in cluster.cluster_info(conn).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@cli_errors
def api_resources_cmd(target: TargetOption = None) -> None:
    """List available API groups and versions."""
    conn, _ = get_connection(target)
    rows = cluster.api_resources(conn)
    table = Table(title="API groups")
    for col in ("group", "preferred", "versions"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["group"], r["preferred"], join_opt(r["versions"]))
    console.print(table)
