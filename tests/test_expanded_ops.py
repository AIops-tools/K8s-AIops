"""Tests for the expanded k8s-aiops ops surface against MOCKED clients.

Covers at least one read tool per new module, the security-critical redaction of
secret VALUES in ``secret_list``, ``set_deployment_image`` BEFORE-state capture
(and its undo descriptor), ``scale_statefulset`` undo, and the
metrics-server-absent graceful path. No real cluster is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException


def _meta(name="x", namespace="default", **kw):
    return SimpleNamespace(
        name=name, namespace=namespace, creation_timestamp=None,
        labels=kw.get("labels"), annotations=kw.get("annotations"),
        owner_references=kw.get("owner_references"),
    )


# ── controllers ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_statefulset_list_reads_summary():
    from k8s_aiops.ops import controllers as ops

    sts = SimpleNamespace(
        metadata=_meta("db"),
        spec=SimpleNamespace(replicas=3, service_name="db"),
        status=SimpleNamespace(ready_replicas=2, current_replicas=3),
    )
    conn = MagicMock()
    conn.apps.list_stateful_set_for_all_namespaces.return_value = SimpleNamespace(items=[sts])
    rows = ops.list_statefulsets(conn)
    assert rows[0]["name"] == "db"
    assert rows[0]["desired"] == 3
    assert rows[0]["ready"] == 2


@pytest.mark.unit
def test_scale_statefulset_captures_previous():
    from k8s_aiops.ops import controllers as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_stateful_set_scale.return_value = SimpleNamespace(
        spec=SimpleNamespace(replicas=2)
    )
    result = ops.scale_statefulset(conn, "db", 5, "prod")
    assert result["previous_replicas"] == 2
    assert result["replicas"] == 5


# ── batch ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_job_list_reads_summary():
    from k8s_aiops.ops import batch as ops

    job = SimpleNamespace(
        metadata=_meta("backup"),
        spec=SimpleNamespace(completions=1, parallelism=1),
        status=SimpleNamespace(succeeded=1, failed=0, active=0),
    )
    conn = MagicMock()
    conn.batch.list_job_for_all_namespaces.return_value = SimpleNamespace(items=[job])
    rows = ops.list_jobs(conn)
    assert rows[0]["name"] == "backup"
    assert rows[0]["succeeded"] == 1


# ── config resources: SECRET REDACTION ────────────────────────────────────


@pytest.mark.unit
def test_secret_list_never_returns_values():
    """Security: secret_list exposes key NAMES only, never values."""
    from k8s_aiops.ops import config_resources as ops

    secret = SimpleNamespace(
        metadata=_meta("db-creds", "prod"),
        type="Opaque",
        data={"password": "c3VwZXJzZWNyZXQ=", "username": "YWRtaW4="},
    )
    conn = MagicMock()
    conn.core.list_secret_for_all_namespaces.return_value = SimpleNamespace(items=[secret])
    rows = ops.list_secrets(conn)
    row = rows[0]
    assert row["name"] == "db-creds"
    assert row["type"] == "Opaque"
    assert sorted(row["key_names"]) == ["password", "username"]
    assert row["values"] == "<redacted>"
    # The base64 secret material must appear NOWHERE in the output.
    flat = repr(rows)
    assert "c3VwZXJzZWNyZXQ" not in flat
    assert "YWRtaW4" not in flat


@pytest.mark.unit
def test_configmap_get_returns_values():
    from k8s_aiops.ops import config_resources as ops

    cm = SimpleNamespace(metadata=_meta("app-config"), data={"LOG_LEVEL": "info"})
    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.core.read_namespaced_config_map.return_value = cm
    result = ops.get_configmap(conn, "app-config")
    assert result["data"]["LOG_LEVEL"] == "info"
    assert result["keys"] == ["LOG_LEVEL"]


# ── storage ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pvc_list_reads_summary():
    from k8s_aiops.ops import storage as ops

    pvc = SimpleNamespace(
        metadata=_meta("data-0", "prod"),
        spec=SimpleNamespace(
            volume_name="pv-1", storage_class_name="standard",
            resources=SimpleNamespace(requests={"storage": "10Gi"}), access_modes=["RWO"],
        ),
        status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
    )
    conn = MagicMock()
    conn.core.list_persistent_volume_claim_for_all_namespaces.return_value = SimpleNamespace(
        items=[pvc]
    )
    rows = ops.list_pvcs(conn)
    assert rows[0]["name"] == "data-0"
    assert rows[0]["status"] == "Bound"
    assert rows[0]["capacity"] == "10Gi"


# ── networking ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_ingress_list_reads_hosts():
    from k8s_aiops.ops import networking as ops

    rule = SimpleNamespace(host="app.example.com", http=None)
    ing = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(ingress_class_name="nginx", rules=[rule]),
    )
    conn = MagicMock()
    conn.networking.list_ingress_for_all_namespaces.return_value = SimpleNamespace(items=[ing])
    rows = ops.list_ingresses(conn)
    assert rows[0]["hosts"] == ["app.example.com"]
    assert rows[0]["class"] == "nginx"


# ── describe ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pod_describe_includes_container_state_and_events():
    from k8s_aiops.ops import describe as ops

    cs = SimpleNamespace(
        name="app", ready=False, restart_count=7,
        image="nginx:1.25",
        state=SimpleNamespace(
            running=None,
            waiting=SimpleNamespace(reason="CrashLoopBackOff"),
            terminated=None,
        ),
    )
    pod = SimpleNamespace(
        metadata=_meta("web-1", "prod"),
        spec=SimpleNamespace(node_name="node-a"),
        status=SimpleNamespace(
            phase="Running", pod_ip="10.1.2.3",
            conditions=[SimpleNamespace(type="Ready", status="False", reason="ContainersNotReady")],
            container_statuses=[cs],
        ),
    )
    ev = SimpleNamespace(
        type="Warning", reason="BackOff", message="Back-off restarting",
        last_timestamp=None, metadata=SimpleNamespace(creation_timestamp=None),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.core.read_namespaced_pod.return_value = pod
    conn.core.list_namespaced_event.return_value = SimpleNamespace(items=[ev])
    result = ops.pod_describe(conn, "web-1", "prod")
    assert result["containers"][0]["restarts"] == 7
    assert "CrashLoopBackOff" in result["containers"][0]["state"]
    assert result["events"][0]["reason"] == "BackOff"


@pytest.mark.unit
def test_node_describe_includes_taints_and_capacity():
    from k8s_aiops.ops import describe as ops

    node = SimpleNamespace(
        metadata=_meta("node-a"),
        spec=SimpleNamespace(
            unschedulable=True,
            taints=[SimpleNamespace(key="dedicated", value="gpu", effect="NoSchedule")],
        ),
        status=SimpleNamespace(
            capacity={"cpu": "8", "memory": "32Gi"},
            allocatable={"cpu": "7800m", "memory": "30Gi"},
            conditions=[SimpleNamespace(type="Ready", status="True", reason="KubeletReady")],
        ),
    )
    conn = MagicMock()
    conn.core.read_node.return_value = node
    result = ops.node_describe(conn, "node-a")
    assert result["schedulable"] is False
    assert result["capacity"]["cpu"] == "8"
    assert result["taints"][0]["effect"] == "NoSchedule"


# ── cluster ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cluster_info_summarizes_health():
    from k8s_aiops.ops import cluster as ops

    ready = SimpleNamespace(
        status=SimpleNamespace(conditions=[SimpleNamespace(type="Ready", status="True")])
    )
    notready = SimpleNamespace(
        status=SimpleNamespace(conditions=[SimpleNamespace(type="Ready", status="False")])
    )
    conn = MagicMock()
    conn.version.get_code.return_value = SimpleNamespace(
        git_version="v1.30.1", platform="linux/amd64"
    )
    conn.core.list_node.return_value = SimpleNamespace(items=[ready, notready])
    conn.core.list_namespace.return_value = SimpleNamespace(items=[1, 2, 3])
    info = ops.cluster_info(conn)
    assert info["server_version"] == "v1.30.1"
    assert info["node_count"] == 2
    assert info["ready_nodes"] == 1
    assert info["namespace_count"] == 3


# ── rollout: set_deployment_image BEFORE-state capture ─────────────────────


def _deployment_with_container(name, image):
    container = SimpleNamespace(name=name, image=image)
    template = SimpleNamespace(
        metadata=SimpleNamespace(labels={}), spec=SimpleNamespace(containers=[container])
    )
    return SimpleNamespace(
        metadata=_meta("web", annotations={"deployment.kubernetes.io/revision": "3"}),
        spec=SimpleNamespace(template=template, replicas=2, paused=False),
        status=SimpleNamespace(),
    )


@pytest.mark.unit
def test_set_deployment_image_captures_previous_image():
    from k8s_aiops.ops import rollout as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment.return_value = _deployment_with_container(
        "app", "nginx:1.25"
    )
    result = ops.set_deployment_image(conn, "web", "app", "nginx:1.27", "prod")
    assert result["previous_image"] == "nginx:1.25"
    assert result["image"] == "nginx:1.27"


@pytest.mark.unit
def test_set_deployment_image_unknown_container_errors():
    from k8s_aiops.ops import rollout as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment.return_value = _deployment_with_container(
        "app", "nginx:1.25"
    )
    with pytest.raises(ValueError, match="not found"):
        ops.set_deployment_image(conn, "web", "missing", "nginx:1.27", "prod")


@pytest.mark.unit
def test_set_deployment_image_records_undo_to_previous(monkeypatch):
    """The MCP wrapper records an inverse restoring the captured previous image."""
    import k8s_aiops.governance.undo as undo_mod
    from mcp_server.tools import rollout as rollout_tools

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment.return_value = _deployment_with_container(
        "app", "nginx:1.25"
    )
    monkeypatch.setattr(rollout_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-img"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = rollout_tools.set_deployment_image(
        name="web", container="app", image="nginx:1.27", namespace="prod"
    )
    assert "error" not in result
    assert recorded["descriptor"]["tool"] == "set_deployment_image"
    assert recorded["descriptor"]["params"]["image"] == "nginx:1.25"
    assert result.get("_undo_id") == "undo-img"


@pytest.mark.unit
def test_rollout_status_reads_replica_counts():
    from k8s_aiops.ops import rollout as ops

    dep = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(replicas=4, paused=True, template=None),
        status=SimpleNamespace(
            updated_replicas=2, ready_replicas=2, available_replicas=2, unavailable_replicas=2
        ),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment.return_value = dep
    result = ops.rollout_status(conn, "web", "prod")
    assert result["desired"] == 4
    assert result["paused"] is True
    assert result["unavailable"] == 2


# ── metrics: graceful absence of metrics-server ────────────────────────────


@pytest.mark.unit
def test_node_top_handles_missing_metrics_server():
    from k8s_aiops.ops import metrics as ops

    conn = MagicMock()
    conn.custom.list_cluster_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    result = ops.node_top(conn)
    assert result["available"] is False
    assert "metrics-server" in result["message"]
    assert result["items"] == []


@pytest.mark.unit
def test_pod_top_returns_usage_when_available():
    from k8s_aiops.ops import metrics as ops

    conn = MagicMock()
    conn.custom.list_cluster_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "web-1", "namespace": "prod"},
                "containers": [{"name": "app", "usage": {"cpu": "12m", "memory": "50Mi"}}],
            }
        ]
    }
    result = ops.pod_top(conn)
    assert result["available"] is True
    assert result["items"][0]["containers"][0]["cpu"] == "12m"


# ── drain skips daemonset/mirror pods ──────────────────────────────────────


@pytest.mark.unit
def test_drain_node_skips_daemonset_pods():
    from k8s_aiops.ops import lifecycle as ops

    ds_pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="ds-1", namespace="kube-system", annotations={},
            owner_references=[SimpleNamespace(kind="DaemonSet", name="kube-proxy")],
        )
    )
    app_pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="web-1", namespace="prod", annotations={},
            owner_references=[SimpleNamespace(kind="ReplicaSet", name="web-abc")],
        )
    )
    conn = MagicMock()
    conn.list_pod_for_all_namespaces = None
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[ds_pod, app_pod])
    result = ops.drain_node(conn, "node-a")
    assert result["cordoned"] is True
    assert any("web-1" in e for e in result["evicted"])
    assert any("ds-1" in s for s in result["skipped"])
    conn.core.create_namespaced_pod_eviction.assert_called_once()


# ── init wizard helpers ────────────────────────────────────────────────────


@pytest.mark.unit
def test_init_list_contexts_handles_missing_kubeconfig(monkeypatch):
    from kubernetes.config.config_exception import ConfigException

    import k8s_aiops.cli.init as init_mod

    def _boom():
        raise ConfigException("no config")

    # Patch the kubernetes config loader used inside _list_contexts.
    import kubernetes.config as kcfg

    monkeypatch.setattr(kcfg, "list_kube_config_contexts", _boom)
    with pytest.raises(RuntimeError, match="No kubeconfig"):
        init_mod._list_contexts()


@pytest.mark.unit
def test_init_write_and_load_targets_roundtrip(monkeypatch, tmp_path):
    import k8s_aiops.cli.init as init_mod

    cfg_dir = tmp_path / ".k8s-aiops"
    cfg_file = cfg_dir / "config.yaml"
    monkeypatch.setattr(init_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(init_mod, "CONFIG_FILE", cfg_file)

    init_mod._write_targets([{"name": "prod", "context": "prod-eks", "namespace": "payments"}])
    loaded = init_mod._load_existing_targets()
    assert loaded == [{"name": "prod", "context": "prod-eks", "namespace": "payments"}]
    # Directory must be owner-only (700).
    import stat as _stat

    assert _stat.S_IMODE(cfg_dir.stat().st_mode) == 0o700


@pytest.mark.unit
def test_init_add_target_appends(monkeypatch):
    import k8s_aiops.cli.init as init_mod

    prompts = iter(["lab", "apps"])  # target name, then default namespace
    monkeypatch.setattr(init_mod.typer, "prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr(init_mod.typer, "confirm", lambda *a, **k: True)

    targets: list[dict] = []
    ctx = {"name": "k3s-lab", "context": {"namespace": "default"}}
    ok = init_mod._add_target(targets, set(), ctx)
    assert ok is True
    assert targets[0] == {"name": "lab", "context": "k3s-lab", "namespace": "apps"}


# ── doctor context verification ────────────────────────────────────────────


@pytest.mark.unit
def test_doctor_check_contexts_flags_missing(monkeypatch):
    import k8s_aiops.doctor as doctor_mod

    monkeypatch.setattr(doctor_mod, "_kubeconfig_context_names", lambda: {"prod-eks"})
    config = SimpleNamespace(
        targets=(
            SimpleNamespace(name="prod", context="prod-eks"),
            SimpleNamespace(name="lab", context="missing"),
        )
    )
    assert doctor_mod._check_contexts(config) == 1  # one missing context
