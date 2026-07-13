"""Ops-layer tests for the major WRITE operations (mocked kubernetes client).

Asserts, for each write: WHICH client method is called, with WHAT parameters,
and that before-state needed for undo (previous replica count / revision) is
captured from the API read, not guessed. Complements test_expanded_ops.py
(scale_statefulset / set_deployment_image / drain-skip are covered there).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from k8s_aiops.ops import lifecycle, rollout
from k8s_aiops.ops._shared import _REQUEST_TIMEOUT


def _conn(namespace: str = "default") -> MagicMock:
    conn = MagicMock(name="conn")
    conn.default_namespace.return_value = namespace
    return conn


@pytest.mark.unit
def test_scale_deployment_reads_previous_then_patches():
    conn = _conn()
    conn.apps.read_namespaced_deployment_scale.return_value = SimpleNamespace(
        spec=SimpleNamespace(replicas=3)
    )
    result = lifecycle.scale_deployment(conn, "web", 5, namespace="prod")

    read_args = conn.apps.read_namespaced_deployment_scale.call_args
    assert read_args.args == ("web", "prod")
    patch_args = conn.apps.patch_namespaced_deployment_scale.call_args
    assert patch_args.args == ("web", "prod", {"spec": {"replicas": 5}})
    assert result["previous_replicas"] == 3  # captured before-state, not guessed
    assert result["replicas"] == 5
    assert result["action"] == "scaled"


@pytest.mark.unit
def test_every_write_call_carries_default_request_timeout():
    """The central call() helper must apply _request_timeout so an unresponsive
    apiserver cannot hang a write indefinitely."""
    conn = _conn()
    lifecycle.delete_pod(conn, "web-1", namespace="prod")
    kwargs = conn.core.delete_namespaced_pod.call_args.kwargs
    assert kwargs.get("_request_timeout") == _REQUEST_TIMEOUT


@pytest.mark.unit
def test_delete_pod_calls_client_with_name_and_namespace():
    conn = _conn()
    result = lifecycle.delete_pod(conn, "web-1", namespace="prod")
    assert conn.core.delete_namespaced_pod.call_args.args == ("web-1", "prod")
    assert result == {"name": "web-1", "namespace": "prod", "action": "deleted"}


@pytest.mark.unit
def test_delete_pod_uses_default_namespace_when_omitted():
    conn = _conn(namespace="staging")
    lifecycle.delete_pod(conn, "web-1")
    assert conn.core.delete_namespaced_pod.call_args.args == ("web-1", "staging")


@pytest.mark.unit
def test_delete_deployment_calls_client():
    conn = _conn()
    result = lifecycle.delete_deployment(conn, "web", namespace="prod")
    assert conn.apps.delete_namespaced_deployment.call_args.args == ("web", "prod")
    assert result["action"] == "deleted"


@pytest.mark.unit
def test_rollout_restart_patches_restarted_at_annotation():
    conn = _conn()
    result = lifecycle.rollout_restart_deployment(conn, "web", namespace="prod")
    args = conn.apps.patch_namespaced_deployment.call_args.args
    assert args[0] == "web" and args[1] == "prod"
    anno = args[2]["spec"]["template"]["metadata"]["annotations"]
    assert anno["kubectl.kubernetes.io/restartedAt"] == result["restarted_at"]
    assert result["action"] == "rollout_restarted"


def _replicaset(name: str, owner: str, revision: int, image: str) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            annotations={"deployment.kubernetes.io/revision": str(revision)},
            owner_references=[SimpleNamespace(name=owner, kind="Deployment")],
        ),
        spec=SimpleNamespace(
            template=SimpleNamespace(
                metadata=SimpleNamespace(labels={"app": "web", "pod-template-hash": "abc"}),
                spec=SimpleNamespace(containers=[SimpleNamespace(name="app", image=image)]),
            )
        ),
    )


@pytest.mark.unit
def test_rollout_undo_rolls_back_to_previous_revision():
    """rollout_undo must read the current revision (before-state) and patch the
    pod template back to the highest PRIOR revision's containers."""
    conn = _conn()
    conn.apps.read_namespaced_deployment.return_value = SimpleNamespace(
        metadata=SimpleNamespace(annotations={"deployment.kubernetes.io/revision": "3"})
    )
    conn.apps.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[
            _replicaset("web-1a", "web", 2, "nginx:1.26"),
            _replicaset("web-2b", "web", 3, "nginx:1.27"),
            _replicaset("other-9z", "other", 1, "redis:7"),
        ]
    )
    result = rollout.rollout_undo(conn, "web", namespace="prod")

    args = conn.apps.patch_namespaced_deployment.call_args.args
    assert args[0] == "web" and args[1] == "prod"
    body = args[2]
    assert body["spec"]["template"]["spec"]["containers"] == [
        {"name": "app", "image": "nginx:1.26"}
    ]
    # pod-template-hash must be stripped from the restored labels
    assert "pod-template-hash" not in body["spec"]["template"]["metadata"]["labels"]
    assert result["from_revision"] == 3  # captured before-state
    assert result["rolled_to_revision"] == 2


@pytest.mark.unit
def test_rollout_undo_without_prior_revision_raises():
    conn = _conn()
    conn.apps.read_namespaced_deployment.return_value = SimpleNamespace(
        metadata=SimpleNamespace(annotations={"deployment.kubernetes.io/revision": "1"})
    )
    conn.apps.list_namespaced_replica_set.return_value = SimpleNamespace(
        items=[_replicaset("web-1a", "web", 1, "nginx:1.26")]
    )
    with pytest.raises(ValueError, match="No prior revision"):
        rollout.rollout_undo(conn, "web", namespace="prod")
    conn.apps.patch_namespaced_deployment.assert_not_called()


@pytest.mark.unit
def test_rollout_pause_and_resume_patch_paused_flag():
    conn = _conn()
    rollout.rollout_pause(conn, "web", namespace="prod")
    assert conn.apps.patch_namespaced_deployment.call_args.args == (
        "web", "prod", {"spec": {"paused": True}},
    )
    rollout.rollout_resume(conn, "web", namespace="prod")
    assert conn.apps.patch_namespaced_deployment.call_args.args == (
        "web", "prod", {"spec": {"paused": False}},
    )


@pytest.mark.unit
def test_drain_node_cordons_first_then_evicts_via_eviction_api():
    conn = _conn()
    pod = SimpleNamespace(
        metadata=SimpleNamespace(
            name="web-1", namespace="prod", owner_references=[], annotations={}
        )
    )
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])
    result = lifecycle.drain_node(conn, "node-1")

    # cordon: patch_node with unschedulable=True
    assert conn.core.patch_node.call_args.args == ("node-1", {"spec": {"unschedulable": True}})
    # eviction: policy/v1 Eviction for the pod, in its namespace
    evict_args = conn.core.create_namespaced_pod_eviction.call_args.args
    assert evict_args[0] == "web-1" and evict_args[1] == "prod"
    assert evict_args[2]["kind"] == "Eviction"
    assert result["evicted"] == ["prod/web-1"]
    assert result["action"] == "drained"
