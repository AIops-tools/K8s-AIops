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
    "node_list", "node_describe", "cordon_node", "uncordon_node", "drain_node",
    # namespaces
    "namespace_list", "create_namespace", "delete_namespace",
    # controllers
    "statefulset_list", "statefulset_get", "daemonset_list", "daemonset_get",
    "replicaset_list", "scale_statefulset",
    # batch
    "job_list", "job_get", "cronjob_list", "cronjob_get", "delete_job",
    # config resources
    "configmap_list", "configmap_get", "secret_list",
    # storage
    "pvc_list", "pvc_get", "pv_list", "storageclass_list",
    # networking
    "ingress_list", "ingress_get", "endpoints_list",
    # describe
    "pod_describe",
    # rollout
    "rollout_status", "rollout_history", "rollout_undo_deployment",
    "rollout_pause", "rollout_resume", "set_deployment_image",
    # metrics
    "node_top", "pod_top",
    # cluster
    "cluster_info", "api_resources",
}

WRITE_TOOLS_WITH_UNDO = {
    "scale_deployment", "cordon_node", "uncordon_node", "scale_statefulset",
    "set_deployment_image", "rollout_pause", "rollout_resume", "create_namespace",
}


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
        "k8s_aiops.ops.controllers",
        "k8s_aiops.ops.batch",
        "k8s_aiops.ops.config_resources",
        "k8s_aiops.ops.storage",
        "k8s_aiops.ops.networking",
        "k8s_aiops.ops.describe",
        "k8s_aiops.ops.rollout",
        "k8s_aiops.ops.metrics",
        "k8s_aiops.ops.cluster",
        "k8s_aiops.cli",
        "k8s_aiops.cli._root",
        "k8s_aiops.cli._common",
        "k8s_aiops.cli.pod",
        "k8s_aiops.cli.deployment",
        "k8s_aiops.cli.service",
        "k8s_aiops.cli.node",
        "k8s_aiops.cli.namespace",
        "k8s_aiops.cli.doctor",
        "k8s_aiops.cli.init",
        "k8s_aiops.cli.statefulset",
        "k8s_aiops.cli.daemonset",
        "k8s_aiops.cli.job",
        "k8s_aiops.cli.configmap",
        "k8s_aiops.cli.storage",
        "k8s_aiops.cli.ingress",
        "k8s_aiops.cli.rollout",
        "k8s_aiops.cli.top",
        "k8s_aiops.cli.cluster",
        "mcp_server.server",
        "mcp_server._shared",
        "mcp_server.tools.workloads",
        "mcp_server.tools.lifecycle",
        "mcp_server.tools.nodes",
        "mcp_server.tools.namespaces",
        "mcp_server.tools.controllers",
        "mcp_server.tools.batch",
        "mcp_server.tools.config_resources",
        "mcp_server.tools.storage",
        "mcp_server.tools.networking",
        "mcp_server.tools.describe",
        "mcp_server.tools.rollout",
        "mcp_server.tools.metrics",
        "mcp_server.tools.cluster",
    ):
        importlib.import_module(name)


@pytest.mark.unit
def test_version():
    import k8s_aiops

    assert k8s_aiops.__version__ == "0.2.0"


@pytest.mark.unit
def test_cli_app_builds_and_help_works():
    from k8s_aiops.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in (
        "pod", "deployment", "statefulset", "daemonset", "job", "cronjob",
        "service", "ingress", "configmap", "secret", "storage", "rollout",
        "top", "node", "namespace", "init", "events", "doctor", "cluster-info",
        "api-resources", "mcp",
    ):
        assert sub in result.output


@pytest.mark.unit
def test_cli_leaf_help_triggers_lazy_imports():
    """Recurse into leaf commands so any broken lazy import surfaces."""
    from k8s_aiops.cli import app

    runner = CliRunner()
    for cmd in (
        ["pod", "--help"], ["deployment", "--help"], ["service", "--help"],
        ["node", "--help"], ["namespace", "--help"], ["doctor", "--help"],
        ["statefulset", "--help"], ["daemonset", "--help"], ["job", "--help"],
        ["cronjob", "--help"], ["ingress", "--help"], ["configmap", "--help"],
        ["secret", "--help"], ["storage", "--help"], ["rollout", "--help"],
        ["top", "--help"], ["init", "--help"], ["cluster-info", "--help"],
        ["api-resources", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"
    for cmd in (
        ["pod", "list", "--help"], ["pod", "get", "--help"], ["pod", "logs", "--help"],
        ["pod", "delete", "--help"], ["pod", "describe", "--help"],
        ["deployment", "list", "--help"], ["deployment", "get", "--help"],
        ["deployment", "scale", "--help"], ["deployment", "restart", "--help"],
        ["deployment", "delete", "--help"],
        ["statefulset", "list", "--help"], ["statefulset", "scale", "--help"],
        ["daemonset", "list", "--help"],
        ["job", "list", "--help"], ["job", "delete", "--help"],
        ["cronjob", "list", "--help"],
        ["service", "list", "--help"],
        ["ingress", "list", "--help"], ["ingress", "get", "--help"],
        ["configmap", "list", "--help"], ["configmap", "get", "--help"],
        ["secret", "list", "--help"],
        ["storage", "pvc-list", "--help"], ["storage", "pv-list", "--help"],
        ["storage", "class-list", "--help"],
        ["rollout", "status", "--help"], ["rollout", "undo", "--help"],
        ["rollout", "set-image", "--help"],
        ["top", "node", "--help"], ["top", "pod", "--help"],
        ["node", "list", "--help"], ["node", "cordon", "--help"],
        ["node", "uncordon", "--help"], ["node", "describe", "--help"],
        ["node", "drain", "--help"],
        ["namespace", "list", "--help"], ["namespace", "create", "--help"],
        ["namespace", "delete", "--help"],
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
