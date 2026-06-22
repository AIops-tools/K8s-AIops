"""Smoke tests for the k8s-aiops skeleton.

Proves: every module imports, the CLI Typer app builds and --help works (root
and leaf), the MCP server exposes the expected tools, EVERY MCP tool carries
the k8s-aiops harness marker ``_is_governed_tool``, write tools record undo
descriptors via the harness, and ops work against a MOCKED kubernetes client
(no real cluster needed — ``load_kube_config`` and the Api classes are mocked).
"""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

EXPECTED_TOOLS = {
    # workloads (read)
    "pod_list", "pod_get", "pod_logs", "deployment_list", "deployment_get",
    "service_list", "event_list",
    # lifecycle (write)
    "scale_deployment", "rollout_restart_deployment", "delete_pod", "delete_deployment",
    # nodes
    "node_list", "cordon_node", "uncordon_node",
    # namespaces
    "namespace_list",
}

WRITE_TOOLS_WITH_UNDO = {"scale_deployment", "cordon_node", "uncordon_node"}


@pytest.mark.unit
def test_all_modules_import():
    for name in (
        "k8s_aiops",
        "k8s_aiops.config",
        "k8s_aiops.connection",
        "k8s_aiops.doctor",
        "k8s_aiops.ops._shared",
        "k8s_aiops.ops.workloads",
        "k8s_aiops.ops.lifecycle",
        "k8s_aiops.ops.nodes",
        "k8s_aiops.ops.namespaces",
        "k8s_aiops.cli",
        "k8s_aiops.cli._root",
        "k8s_aiops.cli._common",
        "k8s_aiops.cli.pod",
        "k8s_aiops.cli.deployment",
        "k8s_aiops.cli.service",
        "k8s_aiops.cli.node",
        "k8s_aiops.cli.namespace",
        "k8s_aiops.cli.doctor",
        "mcp_server.server",
        "mcp_server._shared",
        "mcp_server.tools.workloads",
        "mcp_server.tools.lifecycle",
        "mcp_server.tools.nodes",
        "mcp_server.tools.namespaces",
    ):
        importlib.import_module(name)


@pytest.mark.unit
def test_version():
    import k8s_aiops

    assert k8s_aiops.__version__ == "0.1.0"


@pytest.mark.unit
def test_cli_app_builds_and_help_works():
    from k8s_aiops.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("pod", "deployment", "service", "node", "namespace", "events", "doctor", "mcp"):
        assert sub in result.output


@pytest.mark.unit
def test_cli_leaf_help_triggers_lazy_imports():
    """Recurse into leaf commands so any broken lazy import surfaces."""
    from k8s_aiops.cli import app

    runner = CliRunner()
    for cmd in (
        ["pod", "--help"], ["deployment", "--help"], ["service", "--help"],
        ["node", "--help"], ["namespace", "--help"], ["doctor", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"
    for cmd in (
        ["pod", "list", "--help"], ["pod", "get", "--help"], ["pod", "logs", "--help"],
        ["pod", "delete", "--help"],
        ["deployment", "list", "--help"], ["deployment", "get", "--help"],
        ["deployment", "scale", "--help"], ["deployment", "restart", "--help"],
        ["deployment", "delete", "--help"],
        ["service", "list", "--help"],
        ["node", "list", "--help"], ["node", "cordon", "--help"], ["node", "uncordon", "--help"],
        ["namespace", "list", "--help"],
        ["events", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"


@pytest.mark.unit
def test_mcp_list_tools_exposes_expected_tools():
    from mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, f"missing: {EXPECTED_TOOLS - names}"


@pytest.mark.unit
def test_every_mcp_tool_is_governed_by_harness():
    """Every registered tool callable must carry the @governed_tool marker."""
    from mcp_server import _shared

    tool_objs = _shared.mcp._tool_manager._tools
    assert EXPECTED_TOOLS <= set(tool_objs), "tool registry incomplete"
    for name, tool in tool_objs.items():
        fn = getattr(tool, "fn", None)
        assert fn is not None, f"{name} has no fn"
        assert getattr(fn, "_is_governed_tool", False), (
            f"{name} is not wrapped with @governed_tool (harness marker missing)"
        )


def _mock_conn():
    """A connection whose apps/core expose just what the write tools call."""
    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = "default"
    # scale: read current scale -> previous replicas = 3, then patch
    conn.apps.read_namespaced_deployment_scale.return_value = SimpleNamespace(
        spec=SimpleNamespace(replicas=3)
    )
    conn.apps.patch_namespaced_deployment_scale.return_value = None
    conn.core.patch_node.return_value = None
    return conn


@pytest.mark.unit
def test_scale_records_undo_to_previous_replicas(monkeypatch):
    """scale_deployment records a scale-back-to-previous inverse with _undo_id."""
    import k8s_aiops.governance.undo as undo_mod
    from mcp_server.tools import lifecycle as life_tools

    conn = _mock_conn()
    monkeypatch.setattr(life_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-1"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = life_tools.scale_deployment(name="web", replicas=5, namespace="prod")
    assert "error" not in result
    assert result["previous_replicas"] == 3
    assert recorded["descriptor"]["tool"] == "scale_deployment"
    assert recorded["descriptor"]["params"]["replicas"] == 3  # restore previous
    assert result.get("_undo_id") == "undo-1"


@pytest.mark.unit
def test_cordon_records_uncordon_inverse(monkeypatch):
    """cordon_node records an uncordon_node inverse via the harness."""
    import k8s_aiops.governance.undo as undo_mod
    from mcp_server.tools import nodes as node_tools

    conn = _mock_conn()
    monkeypatch.setattr(node_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-2"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = node_tools.cordon_node(name="node-1")
    assert "error" not in result
    assert recorded["descriptor"]["tool"] == "uncordon_node"
    assert recorded["descriptor"]["params"]["name"] == "node-1"


@pytest.mark.unit
def test_ops_use_mocked_kubernetes_client():
    """list_pods works end-to-end against a mocked kubernetes connection."""
    from k8s_aiops.ops import workloads as ops

    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="web-1", namespace="prod", creation_timestamp=None),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[SimpleNamespace(ready=True, restart_count=2)],
            host_ip="10.0.0.1",
            pod_ip="10.1.2.3",
        ),
        spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="app")]),
    )
    conn = MagicMock(name="conn")
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])

    rows = ops.list_pods(conn)
    assert rows[0]["name"] == "web-1"
    assert rows[0]["ready"] == "1/1"
    assert rows[0]["restarts"] == 2
    assert rows[0]["node"] == "node-a"


@pytest.mark.unit
def test_connection_loads_config_and_translates_errors(monkeypatch):
    """K8sConnection loads kubeconfig and translates ApiException to K8sApiError."""
    from kubernetes.client.exceptions import ApiException

    import k8s_aiops.connection as conn_mod
    from k8s_aiops.config import TargetConfig
    from k8s_aiops.connection import K8sApiError, K8sConnection, translate_api_error

    monkeypatch.setattr(conn_mod.k8s_config, "load_kube_config", lambda **k: None)
    monkeypatch.setattr(conn_mod.k8s_client, "ApiClient", lambda *a, **k: object())
    monkeypatch.setattr(conn_mod.k8s_client, "CoreV1Api", lambda *a, **k: MagicMock())
    monkeypatch.setattr(conn_mod.k8s_client, "AppsV1Api", lambda *a, **k: MagicMock())
    monkeypatch.setattr(conn_mod.k8s_client, "VersionApi", lambda *a, **k: MagicMock())
    conn_mod._CONN_APIS.clear()

    conn = K8sConnection(TargetConfig(name="lab", namespace="prod"))
    assert conn.default_namespace() == "prod"

    err = translate_api_error(ApiException(status=404, reason="not found"), "pods/x")
    assert isinstance(err, K8sApiError)
    assert err.status_code == 404
    assert "not found" in str(err).lower()
