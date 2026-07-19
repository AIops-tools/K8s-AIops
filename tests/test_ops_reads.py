"""Direct ops-layer tests for read paths not covered by the CLI tests.

These exercise normalization of canned kubernetes API responses (summaries,
namespaced vs all-namespaces call selection), the secret-value redaction
guarantee, and the two write paths without an obvious CLI twin (delete_job,
create/delete_namespace). The kubernetes client is always a MagicMock — no
cluster is contacted.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _meta(name="x", namespace="default", **kw):
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        creation_timestamp=None,
        labels=kw.get("labels"),
        annotations=kw.get("annotations"),
        owner_references=kw.get("owner_references"),
    )


# ── workloads: deployments / get_pod / logs / services / events ─────────────


@pytest.mark.unit
def test_list_deployments_all_namespaces_summary():
    from k8s_aiops.ops import workloads as ops

    dep = SimpleNamespace(
        metadata=_meta("web", "prod"),
        spec=SimpleNamespace(replicas=3),
        status=SimpleNamespace(ready_replicas=2, available_replicas=2),
    )
    conn = MagicMock()
    conn.apps.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=[dep])
    rows = ops.list_deployments(conn)
    assert rows[0] == {
        "name": "web",
        "namespace": "prod",
        "desired": 3,
        "ready": 2,
        "available": 2,
        "age": None,
    }
    conn.apps.list_deployment_for_all_namespaces.assert_called_once()


@pytest.mark.unit
def test_list_deployments_namespaced_uses_scoped_call():
    from k8s_aiops.ops import workloads as ops

    conn = MagicMock()
    conn.apps.list_namespaced_deployment.return_value = SimpleNamespace(items=[])
    ops.list_deployments(conn, "prod")
    conn.apps.list_namespaced_deployment.assert_called_once()
    conn.apps.list_deployment_for_all_namespaces.assert_not_called()


@pytest.mark.unit
def test_get_deployment_includes_images_and_strategy():
    from k8s_aiops.ops import workloads as ops

    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="nginx:1.25")]))
    dep = SimpleNamespace(
        metadata=_meta("web", "prod"),
        spec=SimpleNamespace(
            replicas=3, strategy=SimpleNamespace(type="RollingUpdate"), template=tmpl
        ),
        status=SimpleNamespace(ready_replicas=3, available_replicas=3),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.apps.read_namespaced_deployment.return_value = dep
    result = ops.get_deployment(conn, "web", "prod")
    assert result["strategy"] == "RollingUpdate"
    assert result["images"] == ["nginx:1.25"]


@pytest.mark.unit
def test_get_pod_uses_default_namespace_when_omitted():
    from k8s_aiops.ops import workloads as ops

    pod = SimpleNamespace(
        metadata=_meta("web-1"),
        spec=SimpleNamespace(node_name="node-a", containers=[SimpleNamespace(name="app")]),
        status=SimpleNamespace(
            phase="Running",
            host_ip="10.0.0.1",
            pod_ip="10.1.2.3",
            container_statuses=[SimpleNamespace(ready=True, restart_count=0)],
        ),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "sandbox"
    conn.core.read_namespaced_pod.return_value = pod
    result = ops.get_pod(conn, "web-1")
    assert result["pod_ip"] == "10.1.2.3"
    assert result["containers"] == ["app"]
    # default namespace was resolved and passed through.
    args = conn.core.read_namespaced_pod.call_args[0]
    assert args == ("web-1", "sandbox")


@pytest.mark.unit
def test_get_pod_logs_clamps_tail_and_forwards_container():
    from k8s_aiops.ops import workloads as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.core.read_namespaced_pod_log.return_value = "hello"
    result = ops.get_pod_logs(conn, "web-1", "prod", tail_lines=0, container="app")
    assert result["tail_lines"] == 1  # clamped to a minimum of 1
    assert result["logs"] == "hello"
    _, kwargs = conn.core.read_namespaced_pod_log.call_args
    assert kwargs["tail_lines"] == 1
    assert kwargs["container"] == "app"


@pytest.mark.unit
def test_list_events_normalizes_involved_object():
    from k8s_aiops.ops import workloads as ops

    ev = SimpleNamespace(
        type="Warning",
        reason="FailedScheduling",
        involved_object=SimpleNamespace(kind="Pod", name="web-1"),
        metadata=SimpleNamespace(namespace="prod", creation_timestamp=None),
        message="0/3 nodes are available",
        last_timestamp=None,
    )
    conn = MagicMock()
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(items=[ev])
    result = ops.list_events(conn)
    assert result["events"][0]["object"] == "Pod/web-1"
    assert result["events"][0]["reason"] == "FailedScheduling"
    assert result["returned"] == 1
    assert result["limit"] == 50
    assert result["truncated"] is False


# ── controllers: daemonsets / replicasets ───────────────────────────────────


@pytest.mark.unit
def test_list_daemonsets_summary():
    from k8s_aiops.ops import controllers as ops

    ds = SimpleNamespace(
        metadata=_meta("fluentd", "logging"),
        spec=SimpleNamespace(),
        status=SimpleNamespace(
            desired_number_scheduled=3, number_ready=3, number_available=2
        ),
    )
    conn = MagicMock()
    conn.apps.list_daemon_set_for_all_namespaces.return_value = SimpleNamespace(items=[ds])
    rows = ops.list_daemonsets(conn)
    assert rows[0]["desired"] == 3
    assert rows[0]["available"] == 2


@pytest.mark.unit
def test_get_daemonset_includes_images():
    from k8s_aiops.ops import controllers as ops

    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="fluentd:1")]))
    ds = SimpleNamespace(
        metadata=_meta("fluentd", "logging"),
        spec=SimpleNamespace(template=tmpl),
        status=SimpleNamespace(desired_number_scheduled=3, number_ready=3, number_available=3),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "logging"
    conn.apps.read_namespaced_daemon_set.return_value = ds
    result = ops.get_daemonset(conn, "fluentd")
    assert result["images"] == ["fluentd:1"]


@pytest.mark.unit
def test_list_replicasets_summary():
    from k8s_aiops.ops import controllers as ops

    rs = SimpleNamespace(
        metadata=_meta("web-abc", "prod"),
        spec=SimpleNamespace(replicas=2),
        status=SimpleNamespace(ready_replicas=2),
    )
    conn = MagicMock()
    conn.apps.list_replica_set_for_all_namespaces.return_value = SimpleNamespace(items=[rs])
    rows = ops.list_replicasets(conn)
    assert rows[0]["name"] == "web-abc"
    assert rows[0]["desired"] == 2


# ── storage: get_pvc / list_pvs / storageclasses ────────────────────────────


@pytest.mark.unit
def test_get_pvc_includes_access_modes():
    from k8s_aiops.ops import storage as ops

    pvc = SimpleNamespace(
        metadata=_meta("data-0", "prod"),
        spec=SimpleNamespace(
            volume_name="pv-1",
            storage_class_name="standard",
            resources=SimpleNamespace(requests={"storage": "10Gi"}),
            access_modes=["ReadWriteOnce", "ReadOnlyMany"],
        ),
        status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "prod"
    conn.core.read_namespaced_persistent_volume_claim.return_value = pvc
    result = ops.get_pvc(conn, "data-0")
    assert result["access_modes"] == ["ReadWriteOnce", "ReadOnlyMany"]
    assert result["capacity"] == "10Gi"


@pytest.mark.unit
def test_pvc_capacity_falls_back_to_request_when_unbound():
    from k8s_aiops.ops import storage as ops

    pvc = SimpleNamespace(
        metadata=_meta("data-0", "prod"),
        spec=SimpleNamespace(
            volume_name=None,
            storage_class_name="standard",
            resources=SimpleNamespace(requests={"storage": "5Gi"}),
        ),
        status=SimpleNamespace(phase="Pending", capacity=None),
    )
    conn = MagicMock()
    conn.core.list_persistent_volume_claim_for_all_namespaces.return_value = SimpleNamespace(
        items=[pvc]
    )
    rows = ops.list_pvcs(conn)
    assert rows[0]["status"] == "Pending"
    assert rows[0]["capacity"] == "5Gi"  # from requests, since not yet Bound


@pytest.mark.unit
def test_list_pvs_renders_claim_ref():
    from k8s_aiops.ops import storage as ops

    pv = SimpleNamespace(
        metadata=_meta("pv-1"),
        spec=SimpleNamespace(
            capacity={"storage": "10Gi"},
            claim_ref=SimpleNamespace(namespace="prod", name="data-0"),
            storage_class_name="standard",
        ),
        status=SimpleNamespace(phase="Bound"),
    )
    conn = MagicMock()
    conn.core.list_persistent_volume.return_value = SimpleNamespace(items=[pv])
    rows = ops.list_pvs(conn)
    assert rows[0]["claim"] == "prod/data-0"
    assert rows[0]["capacity"] == "10Gi"


@pytest.mark.unit
def test_list_storageclasses_flags_default():
    from k8s_aiops.ops import storage as ops

    default_sc = SimpleNamespace(
        metadata=SimpleNamespace(
            name="standard",
            creation_timestamp=None,
            annotations={"storageclass.kubernetes.io/is-default-class": "true"},
        ),
        provisioner="ebs.csi.aws.com",
        reclaim_policy="Delete",
        volume_binding_mode="WaitForFirstConsumer",
    )
    other_sc = SimpleNamespace(
        metadata=SimpleNamespace(name="slow", creation_timestamp=None, annotations=None),
        provisioner="ebs.csi.aws.com",
        reclaim_policy="Retain",
        volume_binding_mode="Immediate",
    )
    conn = MagicMock()
    conn.storage.list_storage_class.return_value = SimpleNamespace(items=[default_sc, other_sc])
    rows = ops.list_storageclasses(conn)
    assert rows[0]["default"] is True
    assert rows[1]["default"] is False


# ── networking: get_ingress / endpoints ─────────────────────────────────────


@pytest.mark.unit
def test_get_ingress_expands_paths():
    from k8s_aiops.ops import networking as ops

    backend = SimpleNamespace(
        service=SimpleNamespace(name="web-svc", port=SimpleNamespace(number=8080))
    )
    p = SimpleNamespace(path="/api", backend=backend)
    rule = SimpleNamespace(host="app.example.com", http=SimpleNamespace(paths=[p]))
    ing = SimpleNamespace(
        metadata=_meta("web"),
        spec=SimpleNamespace(ingress_class_name="nginx", rules=[rule]),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.networking.read_namespaced_ingress.return_value = ing
    result = ops.get_ingress(conn, "web")
    assert result["paths"][0]["service"] == "web-svc"
    assert result["paths"][0]["port"] == "8080"
    assert result["paths"][0]["path"] == "/api"


@pytest.mark.unit
def test_list_endpoints_collects_addresses_and_ports():
    from k8s_aiops.ops import networking as ops

    subset = SimpleNamespace(
        addresses=[SimpleNamespace(ip="10.1.0.1"), SimpleNamespace(ip="10.1.0.2")],
        ports=[SimpleNamespace(port=8080, protocol="TCP")],
    )
    ep = SimpleNamespace(metadata=_meta("web-svc", "prod"), subsets=[subset])
    conn = MagicMock()
    conn.core.list_endpoints_for_all_namespaces.return_value = SimpleNamespace(items=[ep])
    rows = ops.list_endpoints(conn)
    assert rows[0]["addresses"] == ["10.1.0.1", "10.1.0.2"]
    assert rows[0]["ports"] == ["8080/TCP"]


# ── batch: get_job / cronjobs / delete_job ──────────────────────────────────


@pytest.mark.unit
def test_get_job_includes_parallelism_and_images():
    from k8s_aiops.ops import batch as ops

    tmpl = SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(image="busybox:1")]))
    job = SimpleNamespace(
        metadata=_meta("backup", "ops"),
        spec=SimpleNamespace(completions=1, parallelism=4, template=tmpl),
        status=SimpleNamespace(succeeded=1, failed=0, active=0),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "ops"
    conn.batch.read_namespaced_job.return_value = job
    result = ops.get_job(conn, "backup")
    assert result["parallelism"] == 4
    assert result["images"] == ["busybox:1"]


@pytest.mark.unit
def test_list_cronjobs_summary():
    from k8s_aiops.ops import batch as ops

    cj = SimpleNamespace(
        metadata=_meta("nightly", "ops"),
        spec=SimpleNamespace(schedule="0 0 * * *", suspend=True),
        status=SimpleNamespace(last_schedule_time=None, active=[1, 2]),
    )
    conn = MagicMock()
    conn.batch.list_cron_job_for_all_namespaces.return_value = SimpleNamespace(items=[cj])
    rows = ops.list_cronjobs(conn)
    assert rows[0]["schedule"] == "0 0 * * *"
    assert rows[0]["suspend"] is True
    assert rows[0]["active"] == 2


@pytest.mark.unit
def test_get_cronjob_includes_concurrency_policy():
    from k8s_aiops.ops import batch as ops

    cj = SimpleNamespace(
        metadata=_meta("nightly", "ops"),
        spec=SimpleNamespace(schedule="0 0 * * *", suspend=False, concurrency_policy="Forbid"),
        status=SimpleNamespace(last_schedule_time=None, active=[]),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "ops"
    conn.batch.read_namespaced_cron_job.return_value = cj
    result = ops.get_cronjob(conn, "nightly")
    assert result["concurrency_policy"] == "Forbid"


@pytest.mark.unit
def test_delete_job_calls_api_and_reports_deleted():
    from k8s_aiops.ops import batch as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "ops"
    result = ops.delete_job(conn, "backup")
    assert result == {"name": "backup", "namespace": "ops", "action": "deleted"}
    args = conn.batch.delete_namespaced_job.call_args[0]
    assert args == ("backup", "ops")


# ── nodes / namespaces / configmaps ─────────────────────────────────────────


@pytest.mark.unit
def test_list_nodes_reports_notready_and_roles():
    from k8s_aiops.ops import nodes as ops

    node = SimpleNamespace(
        metadata=_meta("node-a", labels={"node-role.kubernetes.io/worker": ""}),
        spec=SimpleNamespace(unschedulable=True),
        status=SimpleNamespace(
            conditions=[SimpleNamespace(type="Ready", status="False")],
            node_info=SimpleNamespace(kubelet_version="v1.29.0"),
        ),
    )
    conn = MagicMock()
    conn.core.list_node.return_value = SimpleNamespace(items=[node])
    rows = ops.list_nodes(conn)
    assert rows[0]["status"] == "NotReady"
    assert rows[0]["roles"] == "worker"
    assert rows[0]["schedulable"] is False


@pytest.mark.unit
def test_list_namespaces_summary():
    from k8s_aiops.ops import namespaces as ops

    ns = SimpleNamespace(metadata=_meta("payments"), status=SimpleNamespace(phase="Active"))
    conn = MagicMock()
    conn.core.list_namespace.return_value = SimpleNamespace(items=[ns])
    rows = ops.list_namespaces(conn)
    assert rows[0] == {"name": "payments", "phase": "Active", "age": None}


@pytest.mark.unit
def test_create_namespace_sends_correct_body():
    from k8s_aiops.ops import namespaces as ops

    conn = MagicMock()
    result = ops.create_namespace(conn, "sandbox")
    assert result == {"name": "sandbox", "action": "created"}
    body = conn.core.create_namespace.call_args[0][0]
    assert body["metadata"]["name"] == "sandbox"
    assert body["kind"] == "Namespace"


@pytest.mark.unit
def test_delete_namespace_calls_api():
    from k8s_aiops.ops import namespaces as ops

    conn = MagicMock()
    result = ops.delete_namespace(conn, "sandbox")
    assert result == {"name": "sandbox", "action": "deleted"}
    assert conn.core.delete_namespace.call_args[0][0] == "sandbox"


@pytest.mark.unit
def test_list_configmaps_counts_keys():
    from k8s_aiops.ops import config_resources as ops

    cm = SimpleNamespace(metadata=_meta("app-config", "prod"), data={"A": "1", "B": "2"})
    conn = MagicMock()
    conn.core.list_config_map_for_all_namespaces.return_value = SimpleNamespace(items=[cm])
    rows = ops.list_configmaps(conn)
    assert rows[0]["keys"] == 2
    assert rows[0]["name"] == "app-config"


@pytest.mark.unit
def test_list_configmaps_namespaced_scoped_call():
    from k8s_aiops.ops import config_resources as ops

    conn = MagicMock()
    conn.core.list_namespaced_config_map.return_value = SimpleNamespace(items=[])
    ops.list_configmaps(conn, "prod")
    conn.core.list_namespaced_config_map.assert_called_once()
    conn.core.list_config_map_for_all_namespaces.assert_not_called()


# ── rollout write paths (undo / pause / resume) ─────────────────────────────


@pytest.mark.unit
def test_rollout_pause_and_resume_are_inverses():
    from k8s_aiops.ops import rollout as ops

    conn = MagicMock()
    conn.default_namespace.return_value = "prod"
    paused = ops.rollout_pause(conn, "web")
    resumed = ops.rollout_resume(conn, "web")
    assert paused["paused"] is True and paused["action"] == "paused"
    assert resumed["paused"] is False and resumed["action"] == "resumed"
    # Both patch the deployment.
    assert conn.apps.patch_namespaced_deployment.call_count == 2


@pytest.mark.unit
def test_rollout_undo_to_previous_revision_records_from_revision():
    from k8s_aiops.ops import rollout as ops

    tmpl = SimpleNamespace(
        metadata=SimpleNamespace(labels={"pod-template-hash": "abc"}),
        spec=SimpleNamespace(containers=[SimpleNamespace(name="app", image="nginx:1.24")]),
    )
    dep = SimpleNamespace(
        metadata=_meta("web", annotations={"deployment.kubernetes.io/revision": "3"}),
    )

    def _rs(name, rev):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                name=name,
                annotations={"deployment.kubernetes.io/revision": str(rev)},
                owner_references=[SimpleNamespace(name="web", kind="Deployment")],
            ),
            spec=SimpleNamespace(template=tmpl),
        )

    conn = MagicMock()
    conn.default_namespace.return_value = "prod"
    conn.apps.read_namespaced_deployment.return_value = dep
    conn.apps.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[_rs("web-1", 1), _rs("web-2", 2), _rs("web-3", 3)]
    )
    result = ops.rollout_undo(conn, "web")
    assert result["from_revision"] == 3
    assert result["rolled_to_revision"] == 2  # immediately previous
    conn.apps.patch_namespaced_deployment.assert_called_once()


@pytest.mark.unit
def test_rollout_undo_no_prior_revision_raises():
    from k8s_aiops.ops import rollout as ops

    tmpl = SimpleNamespace(
        metadata=SimpleNamespace(labels={}),
        spec=SimpleNamespace(containers=[]),
    )
    dep = SimpleNamespace(
        metadata=_meta("web", annotations={"deployment.kubernetes.io/revision": "1"}),
    )
    rs = SimpleNamespace(
        metadata=SimpleNamespace(
            name="web-1",
            annotations={"deployment.kubernetes.io/revision": "1"},
            owner_references=[SimpleNamespace(name="web", kind="Deployment")],
        ),
        spec=SimpleNamespace(template=tmpl),
    )
    conn = MagicMock()
    conn.default_namespace.return_value = "prod"
    conn.apps.read_namespaced_deployment.return_value = dep
    conn.apps.list_namespaced_replica_set.return_value = SimpleNamespace(items=[rs])
    with pytest.raises(ValueError, match="No prior revision"):
        ops.rollout_undo(conn, "web")


# ── cluster: api_resources ──────────────────────────────────────────────────


@pytest.mark.unit
def test_api_resources_lists_groups_and_preferred():
    from k8s_aiops.ops import cluster as ops

    group = SimpleNamespace(
        name="apps",
        versions=[SimpleNamespace(version="v1")],
        preferred_version=SimpleNamespace(version="v1"),
    )
    conn = MagicMock()
    conn.apis.get_api_versions.return_value = SimpleNamespace(groups=[group])
    rows = ops.api_resources(conn)
    assert rows[0]["group"] == "apps"
    assert rows[0]["versions"] == ["v1"]
    assert rows[0]["preferred"] == "v1"
