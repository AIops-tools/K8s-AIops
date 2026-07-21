"""CLI read command bodies against MOCKED connections.

Each test patches ``get_connection`` in the CLI sub-module so the command runs
its real body (table build / detail print) AND drives the real ops function,
which reads from a MagicMock kubernetes client. Assertions check the rendered
output and that the correct kubernetes API method was invoked.

No governance side effects are exercised here. ``--dry-run`` previews now route
through the governed twin — they are audited writes-that-never-write, so they
live in test_cli_writes.py where a temp ``K8S_AIOPS_HOME`` is bound.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _meta(name="x", namespace="default", **kw):
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        creation_timestamp=None,
        labels=kw.get("labels"),
        annotations=kw.get("annotations"),
        owner_references=kw.get("owner_references"),
    )


def _patch_conn(monkeypatch, module_path: str) -> MagicMock:
    """Patch get_connection in a CLI sub-module; return the mock conn."""
    import importlib

    mod = importlib.import_module(module_path)
    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = "default"
    monkeypatch.setattr(mod, "get_connection", lambda target=None: (conn, None))
    return conn


# ── node ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_node_list_renders_rows(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.node")
    node = SimpleNamespace(
        metadata=_meta("node-a", labels={"node-role.kubernetes.io/control-plane": ""}),
        spec=SimpleNamespace(unschedulable=False),
        status=SimpleNamespace(
            conditions=[SimpleNamespace(type="Ready", status="True")],
            node_info=SimpleNamespace(kubelet_version="v1.30.1"),
        ),
    )
    conn.core.list_node.return_value = SimpleNamespace(items=[node])
    result = runner.invoke(app, ["node", "list"])
    assert result.exit_code == 0, result.output
    assert "node-a" in result.output
    assert "control-plane" in result.output
    conn.core.list_node.assert_called_once()


@pytest.mark.unit
def test_cli_node_describe_prints_taints(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.node")
    node = SimpleNamespace(
        metadata=_meta("node-a"),
        spec=SimpleNamespace(
            unschedulable=True,
            taints=[SimpleNamespace(key="gpu", value="a100", effect="NoSchedule")],
        ),
        status=SimpleNamespace(
            capacity={"cpu": "8"},
            allocatable={"cpu": "7500m"},
            conditions=[SimpleNamespace(type="Ready", status="True", reason="KubeletReady")],
        ),
    )
    conn.core.read_node.return_value = node
    result = runner.invoke(app, ["node", "describe", "node-a"])
    assert result.exit_code == 0, result.output
    assert "NoSchedule" in result.output
    assert "KubeletReady" in result.output


@pytest.mark.unit
def test_cli_node_uncordon_calls_gov(monkeypatch):
    from k8s_aiops.cli import app
    from mcp_server.tools import nodes as gov

    _patch_conn(monkeypatch, "k8s_aiops.cli.node")
    monkeypatch.setattr(
        gov, "uncordon_node", lambda **k: {"name": k["name"], "action": "uncordoned"}
    )
    result = runner.invoke(app, ["node", "uncordon", "node-a"])
    assert result.exit_code == 0, result.output
    assert "uncordoned" in result.output


# ── pod ─────────────────────────────────────────────────────────────────────


def _pod(name="web-1", ns="prod", restarts=3):
    cs = SimpleNamespace(ready=True, restart_count=restarts, name="app")
    return SimpleNamespace(
        metadata=_meta(name, ns),
        spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="app")]),
        status=SimpleNamespace(
            phase="Running",
            host_ip="10.0.0.1",
            pod_ip="10.1.2.3",
            container_statuses=[cs],
        ),
    )


@pytest.mark.unit
def test_cli_pod_list_renders_rows(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.pod")
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[_pod()])
    result = runner.invoke(app, ["pod", "list"])
    assert result.exit_code == 0, result.output
    assert "web-1" in result.output
    conn.core.list_pod_for_all_namespaces.assert_called_once()


@pytest.mark.unit
def test_cli_pod_list_namespaced_uses_scoped_call(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.pod")
    conn.core.list_namespaced_pod.return_value = SimpleNamespace(items=[_pod()])
    result = runner.invoke(app, ["pod", "list", "-n", "prod"])
    assert result.exit_code == 0, result.output
    conn.core.list_namespaced_pod.assert_called_once()
    conn.core.list_pod_for_all_namespaces.assert_not_called()


@pytest.mark.unit
def test_cli_pod_get_prints_detail(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.pod")
    conn.core.read_namespaced_pod.return_value = _pod()
    result = runner.invoke(app, ["pod", "get", "web-1", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert "10.1.2.3" in result.output
    conn.core.read_namespaced_pod.assert_called_once()


@pytest.mark.unit
def test_cli_pod_logs_prints_lines(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.pod")
    conn.core.read_namespaced_pod_log.return_value = "line-a\nline-b"
    result = runner.invoke(app, ["pod", "logs", "web-1", "-n", "prod", "--tail", "10"])
    assert result.exit_code == 0, result.output
    assert "line-a" in result.output
    # tail_lines forwarded to the client.
    _, kwargs = conn.core.read_namespaced_pod_log.call_args
    assert kwargs["tail_lines"] == 10


# ── top ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_top_node_renders_usage(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.top")
    conn.custom.list_cluster_custom_object.return_value = {
        "items": [{"metadata": {"name": "node-a"}, "usage": {"cpu": "250m", "memory": "1Gi"}}]
    }
    result = runner.invoke(app, ["top", "node"])
    assert result.exit_code == 0, result.output
    assert "node-a" in result.output
    assert "250m" in result.output


@pytest.mark.unit
def test_cli_top_node_reports_absent_metrics_server(monkeypatch):
    from kubernetes.client.exceptions import ApiException

    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.top")
    conn.custom.list_cluster_custom_object.side_effect = ApiException(status=404, reason="NF")
    result = runner.invoke(app, ["top", "node"])
    assert result.exit_code == 0, result.output
    assert "metrics-server" in result.output


@pytest.mark.unit
def test_cli_top_pod_renders_container_usage(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.top")
    conn.custom.list_namespaced_custom_object.return_value = {
        "items": [
            {
                "metadata": {"name": "web-1", "namespace": "prod"},
                "containers": [{"name": "app", "usage": {"cpu": "12m", "memory": "50Mi"}}],
            }
        ]
    }
    result = runner.invoke(app, ["top", "pod", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert "web-1" in result.output
    assert "12m" in result.output
    conn.custom.list_namespaced_custom_object.assert_called_once()


# ── storage ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_storage_pvc_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.storage")
    pvc = SimpleNamespace(
        metadata=_meta("data-0", "prod"),
        spec=SimpleNamespace(
            volume_name="pv-1",
            storage_class_name="standard",
            resources=SimpleNamespace(requests={"storage": "10Gi"}),
        ),
        status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
    )
    conn.core.list_persistent_volume_claim_for_all_namespaces.return_value = SimpleNamespace(
        items=[pvc]
    )
    result = runner.invoke(app, ["storage", "pvc-list"])
    assert result.exit_code == 0, result.output
    assert "data-0" in result.output
    assert "Bound" in result.output


@pytest.mark.unit
def test_cli_storage_pvc_get_prints_access_modes(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.storage")
    pvc = SimpleNamespace(
        metadata=_meta("data-0", "prod"),
        spec=SimpleNamespace(
            volume_name="pv-1",
            storage_class_name="standard",
            resources=SimpleNamespace(requests={"storage": "10Gi"}),
            access_modes=["ReadWriteOnce"],
        ),
        status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
    )
    conn.core.read_namespaced_persistent_volume_claim.return_value = pvc
    result = runner.invoke(app, ["storage", "pvc-get", "data-0", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert "ReadWriteOnce" in result.output


@pytest.mark.unit
def test_cli_storage_pv_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.storage")
    claim = SimpleNamespace(namespace="prod", name="data-0")
    pv = SimpleNamespace(
        metadata=_meta("pv-1"),
        spec=SimpleNamespace(
            capacity={"storage": "10Gi"},
            claim_ref=claim,
            storage_class_name="standard",
        ),
        status=SimpleNamespace(phase="Bound"),
    )
    conn.core.list_persistent_volume.return_value = SimpleNamespace(items=[pv])
    result = runner.invoke(app, ["storage", "pv-list"])
    assert result.exit_code == 0, result.output
    assert "pv-1" in result.output
    assert "prod/data-0" in result.output


@pytest.mark.unit
def test_cli_storage_class_list_marks_default(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.storage")
    sc = SimpleNamespace(
        metadata=SimpleNamespace(
            name="standard",
            creation_timestamp=None,
            annotations={"storageclass.kubernetes.io/is-default-class": "true"},
        ),
        provisioner="kubernetes.io/aws-ebs",
        reclaim_policy="Delete",
        volume_binding_mode="Immediate",
    )
    conn.storage.list_storage_class.return_value = SimpleNamespace(items=[sc])
    result = runner.invoke(app, ["storage", "class-list"])
    assert result.exit_code == 0, result.output
    assert "standard" in result.output
    assert "True" in result.output  # default flag rendered


# ── job / cronjob ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_job_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.job")
    job = SimpleNamespace(
        metadata=_meta("backup", "ops"),
        spec=SimpleNamespace(completions=1, parallelism=1),
        status=SimpleNamespace(succeeded=1, failed=0, active=0),
    )
    conn.batch.list_job_for_all_namespaces.return_value = SimpleNamespace(items=[job])
    result = runner.invoke(app, ["job", "list"])
    assert result.exit_code == 0, result.output
    assert "backup" in result.output


@pytest.mark.unit
def test_cli_job_get_prints_images(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.job")
    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="busybox:1")]))
    job = SimpleNamespace(
        metadata=_meta("backup", "ops"),
        spec=SimpleNamespace(completions=1, parallelism=2, template=tmpl),
        status=SimpleNamespace(succeeded=1, failed=0, active=0),
    )
    conn.batch.read_namespaced_job.return_value = job
    result = runner.invoke(app, ["job", "get", "backup", "-n", "ops"])
    assert result.exit_code == 0, result.output
    assert "busybox:1" in result.output


@pytest.mark.unit
def test_cli_cronjob_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.job")
    cj = SimpleNamespace(
        metadata=_meta("nightly", "ops"),
        spec=SimpleNamespace(schedule="0 0 * * *", suspend=False),
        status=SimpleNamespace(last_schedule_time=None, active=[]),
    )
    conn.batch.list_cron_job_for_all_namespaces.return_value = SimpleNamespace(items=[cj])
    result = runner.invoke(app, ["cronjob", "list"])
    assert result.exit_code == 0, result.output
    assert "nightly" in result.output
    assert "0 0" in result.output


@pytest.mark.unit
def test_cli_cronjob_get_prints_concurrency(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.job")
    cj = SimpleNamespace(
        metadata=_meta("nightly", "ops"),
        spec=SimpleNamespace(schedule="0 0 * * *", suspend=False, concurrency_policy="Forbid"),
        status=SimpleNamespace(last_schedule_time=None, active=[]),
    )
    conn.batch.read_namespaced_cron_job.return_value = cj
    result = runner.invoke(app, ["cronjob", "get", "nightly", "-n", "ops"])
    assert result.exit_code == 0, result.output
    assert "Forbid" in result.output


# ── namespace ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_namespace_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.namespace")
    ns = SimpleNamespace(
        metadata=_meta("payments"), status=SimpleNamespace(phase="Active")
    )
    conn.core.list_namespace.return_value = SimpleNamespace(items=[ns])
    result = runner.invoke(app, ["namespace", "list"])
    assert result.exit_code == 0, result.output
    assert "payments" in result.output
    assert "Active" in result.output


# ── ingress ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_ingress_list_joins_hosts(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.ingress")
    rule = SimpleNamespace(host="app.example.com", http=None)
    ing = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(ingress_class_name="nginx", rules=[rule]),
    )
    conn.networking.list_ingress_for_all_namespaces.return_value = SimpleNamespace(items=[ing])
    result = runner.invoke(app, ["ingress", "list"])
    assert result.exit_code == 0, result.output
    assert "app.example.com" in result.output


@pytest.mark.unit
def test_cli_ingress_get_prints_paths(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.ingress")
    backend = SimpleNamespace(
        service=SimpleNamespace(name="web-svc", port=SimpleNamespace(number=8080))
    )
    path = SimpleNamespace(path="/api", backend=backend)
    http = SimpleNamespace(paths=[path])
    rule = SimpleNamespace(host="app.example.com", http=http)
    ing = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(ingress_class_name="nginx", rules=[rule]),
    )
    conn.networking.read_namespaced_ingress.return_value = ing
    result = runner.invoke(app, ["ingress", "get", "web"])
    assert result.exit_code == 0, result.output
    assert "web-svc" in result.output
    assert "/api" in result.output


# ── service ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_service_list_renders_ports(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.service")
    svc = SimpleNamespace(
        metadata=_meta("web-svc", "prod"),
        spec=SimpleNamespace(
            type="ClusterIP",
            cluster_ip="10.96.0.1",
            ports=[SimpleNamespace(port=80, protocol="TCP")],
        ),
    )
    conn.core.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[svc])
    result = runner.invoke(app, ["service", "list"])
    assert result.exit_code == 0, result.output
    assert "web-svc" in result.output
    assert "80/TCP" in result.output


# ── statefulset ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_statefulset_list_renders(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.statefulset")
    sts = SimpleNamespace(
        metadata=_meta("db", "data"),
        spec=SimpleNamespace(replicas=3, service_name="db"),
        status=SimpleNamespace(ready_replicas=3, current_replicas=3),
    )
    conn.apps.list_stateful_set_for_all_namespaces.return_value = SimpleNamespace(items=[sts])
    result = runner.invoke(app, ["statefulset", "list"])
    assert result.exit_code == 0, result.output
    assert "db" in result.output


@pytest.mark.unit
def test_cli_statefulset_get_prints_service_name(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.statefulset")
    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="pg:16")]))
    sts = SimpleNamespace(
        metadata=_meta("db", "data"),
        spec=SimpleNamespace(replicas=3, service_name="db-headless", template=tmpl),
        status=SimpleNamespace(ready_replicas=3, current_replicas=3),
    )
    conn.apps.read_namespaced_stateful_set.return_value = sts
    result = runner.invoke(app, ["statefulset", "get", "db", "-n", "data"])
    assert result.exit_code == 0, result.output
    assert "db-headless" in result.output
    assert "pg:16" in result.output


# ── rollout read ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_rollout_status_prints(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.rollout")
    dep = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(replicas=4, paused=False),
        status=SimpleNamespace(
            updated_replicas=4, ready_replicas=4, available_replicas=4, unavailable_replicas=0
        ),
    )
    conn.apps.read_namespaced_deployment.return_value = dep
    result = runner.invoke(app, ["rollout", "status", "web", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert "desired" in result.output


@pytest.mark.unit
def test_cli_rollout_history_sorts_revisions(monkeypatch):
    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.rollout")
    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="nginx:1.25")]))

    def _rs(name, rev):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                annotations={"deployment.kubernetes.io/revision": str(rev)},
                owner_references=[SimpleNamespace(name="web", kind="Deployment")],
            ),
            spec=SimpleNamespace(template=tmpl),
        )

    conn.apps.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[_rs("web-b", 2), _rs("web-a", 1)]
    )
    result = runner.invoke(app, ["rollout", "history", "web", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert "web-a" in result.output and "web-b" in result.output


# ── top-level: events, cluster-info, api-resources ──────────────────────────


@pytest.mark.unit
def test_cli_events_renders(monkeypatch):
    import k8s_aiops.cli._common as common
    from k8s_aiops.cli import app

    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = "default"
    monkeypatch.setattr(
        common, "get_connection", lambda target=None, config_path=None: (conn, None)
    )
    ev = SimpleNamespace(
        type="Warning",
        reason="BackOff",
        involved_object=SimpleNamespace(kind="Pod", name="web-1"),
        metadata=SimpleNamespace(namespace="prod", creation_timestamp=None),
        message="Back-off restarting failed container",
        last_timestamp=None,
    )
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(items=[ev])
    result = runner.invoke(app, ["events"])
    assert result.exit_code == 0, result.output
    assert "BackOff" in result.output


@pytest.mark.unit
def test_cli_cluster_info_renders(monkeypatch):
    import k8s_aiops.cli.cluster as cluster_cli
    from k8s_aiops.cli import app

    conn = MagicMock(name="conn")
    monkeypatch.setattr(cluster_cli, "get_connection", lambda target=None: (conn, None))
    conn.version.get_code.return_value = SimpleNamespace(
        git_version="v1.30.1", platform="linux/amd64"
    )
    conn.core.list_node.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(
                status=SimpleNamespace(conditions=[SimpleNamespace(type="Ready", status="True")])
            )
        ]
    )
    conn.core.list_namespace.return_value = SimpleNamespace(items=[1, 2])
    result = runner.invoke(app, ["cluster-info"])
    assert result.exit_code == 0, result.output
    assert "v1.30.1" in result.output


# ── teaching-error path through cli_errors ──────────────────────────────────


@pytest.mark.unit
def test_cli_translates_api_error_to_one_line(monkeypatch):
    from kubernetes.client.exceptions import ApiException

    from k8s_aiops.cli import app

    conn = _patch_conn(monkeypatch, "k8s_aiops.cli.pod")
    conn.core.list_pod_for_all_namespaces.side_effect = ApiException(status=403, reason="Forbidden")
    result = runner.invoke(app, ["pod", "list"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "403" in result.output
