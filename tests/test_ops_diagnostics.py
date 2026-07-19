"""Tests for the diagnostics / RCA layer.

Pure heuristics (``k8s_aiops.ops.diagnostics``) are exercised with hand-built
normalized rows — each threshold trip, healthy=clean, worst-first ordering, and
robustness to missing fields. Two tests drive the MCP tools against a mocked
kubernetes client, asserting the harness marker and correct collection.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from k8s_aiops.ops import diagnostics as diag

# ─── pure pod heuristics ──────────────────────────────────────────────────────


def _pod_row(name="p", ns="default", phase="Running", unschedulable=None, containers=None):
    return {
        "name": name,
        "namespace": ns,
        "phase": phase,
        "unschedulable": unschedulable,
        "containers": containers or [],
    }


def _container(
    name="c", ready=True, restarts=0, waiting=None, terminated=None, last_terminated=None
):
    return {
        "name": name,
        "ready": ready,
        "restarts": restarts,
        "waiting": waiting,
        "terminated": terminated,
        "lastTerminated": last_terminated,
    }


@pytest.mark.unit
def test_pod_health_healthy_is_clean():
    rows = [_pod_row(containers=[_container(ready=True, restarts=0)])]
    result = diag.pod_health_findings(rows)
    assert result["findings"] == []
    assert result["podsAnalyzed"] == 1


@pytest.mark.unit
def test_pod_health_crashloop_is_critical():
    rows = [_pod_row(containers=[_container(waiting="CrashLoopBackOff", restarts=7)])]
    findings = diag.pod_health_findings(rows)["findings"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"
    assert findings[0]["signal"] == "CrashLoopBackOff"
    assert "restarts=7" in findings[0]["detail"]


@pytest.mark.unit
@pytest.mark.parametrize("reason", ["ImagePullBackOff", "ErrImagePull"])
def test_pod_health_image_pull_failure_is_critical(reason):
    rows = [_pod_row(containers=[_container(ready=False, waiting=reason)])]
    findings = diag.pod_health_findings(rows)["findings"]
    assert findings[0]["severity"] == "critical"
    assert findings[0]["signal"] == "image pull failure"
    assert reason in findings[0]["detail"]


@pytest.mark.unit
def test_pod_health_oomkilled_from_last_state_is_critical():
    rows = [_pod_row(containers=[_container(last_terminated="OOMKilled", restarts=3)])]
    findings = diag.pod_health_findings(rows)["findings"]
    assert findings[0]["signal"] == "OOMKilled"
    assert findings[0]["severity"] == "critical"


@pytest.mark.unit
def test_pod_health_config_error_is_warning():
    rows = [_pod_row(containers=[_container(waiting="CreateContainerConfigError")])]
    findings = diag.pod_health_findings(rows)["findings"]
    assert findings[0]["signal"] == "container config error"
    assert findings[0]["severity"] == "warning"


@pytest.mark.unit
def test_pod_health_high_restarts_only_when_not_backoff():
    rows = [_pod_row(containers=[_container(restarts=diag.RESTART_HIGH)])]
    findings = diag.pod_health_findings(rows)["findings"]
    assert findings[0]["signal"] == "high restart count"
    assert findings[0]["severity"] == "warning"
    # a crashlooping container is not double-counted as "high restart count"
    rows = [_pod_row(containers=[_container(waiting="CrashLoopBackOff", restarts=99)])]
    signals = [f["signal"] for f in diag.pod_health_findings(rows)["findings"]]
    assert signals == ["CrashLoopBackOff"]


@pytest.mark.unit
def test_pod_health_unschedulable_is_flagged():
    rows = [_pod_row(phase="Pending", unschedulable="Unschedulable")]
    findings = diag.pod_health_findings(rows)["findings"]
    assert findings[0]["signal"] == "unschedulable"
    assert "Unschedulable" in findings[0]["detail"]


@pytest.mark.unit
def test_pod_health_worst_first_ordering():
    rows = [
        _pod_row(name="warn", containers=[_container(restarts=diag.RESTART_HIGH)]),
        _pod_row(name="crit", containers=[_container(waiting="CrashLoopBackOff")]),
    ]
    findings = diag.pod_health_findings(rows)["findings"]
    assert [f["severity"] for f in findings] == ["critical", "warning"]


@pytest.mark.unit
def test_pod_health_missing_fields_robust():
    # empty dict, None containers — must not raise, yields no findings
    assert diag.pod_health_findings([{}])["findings"] == []
    assert diag.pod_health_findings([_pod_row(containers=None)])["findings"] == []


# ─── pure workload heuristics ─────────────────────────────────────────────────


def _wl_row(
    kind="Deployment", name="w", ns="default", desired=3, ready=3, available=3, conditions=None
):
    return {
        "kind": kind,
        "name": name,
        "namespace": ns,
        "desired": desired,
        "ready": ready,
        "available": available,
        "conditions": conditions or [],
    }


@pytest.mark.unit
def test_workload_healthy_is_clean():
    result = diag.workload_readiness_findings([_wl_row()])
    assert result["findings"] == []
    assert result["workloadsAnalyzed"] == 1


@pytest.mark.unit
def test_workload_zero_ready_is_critical():
    findings = diag.workload_readiness_findings([_wl_row(ready=0)])["findings"]
    assert findings[0]["severity"] == "critical"
    assert findings[0]["signal"] == "under-replicated"
    assert "0/3" in findings[0]["detail"]


@pytest.mark.unit
def test_workload_partial_ready_is_warning():
    findings = diag.workload_readiness_findings([_wl_row(ready=1)])["findings"]
    assert findings[0]["severity"] == "warning"
    assert "1/3" in findings[0]["detail"]


@pytest.mark.unit
def test_workload_progressing_false_is_rollout_stuck():
    conds = [{"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}]
    findings = diag.workload_readiness_findings([_wl_row(conditions=conds)])["findings"]
    assert findings[0]["signal"] == "rollout stuck"
    assert findings[0]["severity"] == "critical"
    assert "ProgressDeadlineExceeded" in findings[0]["detail"]


@pytest.mark.unit
def test_workload_available_false_suppressed_when_under_replicated():
    conds = [{"type": "Available", "status": "False", "reason": "MinimumReplicasUnavailable"}]
    findings = diag.workload_readiness_findings([_wl_row(ready=1, conditions=conds)])["findings"]
    signals = {f["signal"] for f in findings}
    assert "under-replicated" in signals and "unavailable" not in signals


@pytest.mark.unit
def test_workload_worst_first_ordering():
    rows = [_wl_row(name="warn", ready=2), _wl_row(name="crit", ready=0)]
    findings = diag.workload_readiness_findings(rows)["findings"]
    assert [f["severity"] for f in findings] == ["critical", "warning"]


@pytest.mark.unit
def test_workload_missing_fields_robust():
    assert diag.workload_readiness_findings([{}])["findings"] == []


# ─── pure transforms ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_pod_to_row_extracts_states():
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="web", namespace="prod"),
        status=SimpleNamespace(
            phase="Pending",
            conditions=[
                SimpleNamespace(type="PodScheduled", status="False", reason="Unschedulable")
            ],
            container_statuses=[
                SimpleNamespace(
                    name="app",
                    ready=False,
                    restart_count=4,
                    state=SimpleNamespace(
                        waiting=SimpleNamespace(reason="CrashLoopBackOff"), terminated=None
                    ),
                    last_state=SimpleNamespace(terminated=SimpleNamespace(reason="OOMKilled")),
                )
            ],
        ),
    )
    row = diag.pod_to_row(pod)
    assert row["name"] == "web"
    assert row["unschedulable"] == "Unschedulable"
    c = row["containers"][0]
    assert c["waiting"] == "CrashLoopBackOff"
    assert c["lastTerminated"] == "OOMKilled"
    assert c["restarts"] == 4


@pytest.mark.unit
def test_workload_to_row_daemonset_uses_daemonset_counts():
    ds = SimpleNamespace(
        metadata=SimpleNamespace(name="fluentd", namespace="kube-system"),
        spec=SimpleNamespace(replicas=None),
        status=SimpleNamespace(
            desired_number_scheduled=5, number_ready=3, number_available=3, conditions=None
        ),
    )
    row = diag.workload_to_row(ds, "DaemonSet")
    assert row["desired"] == 5 and row["ready"] == 3


# ─── MCP tools against a mocked client ────────────────────────────────────────


def _crashloop_pod():
    return SimpleNamespace(
        metadata=SimpleNamespace(name="api", namespace="prod"),
        status=SimpleNamespace(
            phase="Running",
            conditions=None,
            container_statuses=[
                SimpleNamespace(
                    name="api",
                    ready=False,
                    restart_count=9,
                    state=SimpleNamespace(
                        waiting=SimpleNamespace(reason="CrashLoopBackOff"), terminated=None
                    ),
                    last_state=None,
                )
            ],
        ),
    )


@pytest.mark.unit
def test_pod_health_rca_is_governed_and_collects(monkeypatch):
    from mcp_server.tools import diagnostics as diag_tools

    assert diag_tools.pod_health_rca._is_governed_tool is True

    conn = MagicMock(name="conn")
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[_crashloop_pod()])
    monkeypatch.setattr(diag_tools, "_get_connection", lambda target=None: conn)

    result = diag_tools.pod_health_rca()
    assert "error" not in result
    assert result["podsAnalyzed"] == 1
    assert result["findings"][0]["signal"] == "CrashLoopBackOff"
    conn.core.list_pod_for_all_namespaces.assert_called_once()


@pytest.mark.unit
def test_workload_readiness_rca_is_governed_and_collects(monkeypatch):
    from mcp_server.tools import diagnostics as diag_tools

    assert diag_tools.workload_readiness_rca._is_governed_tool is True

    dep = SimpleNamespace(
        metadata=SimpleNamespace(name="web", namespace="prod"),
        spec=SimpleNamespace(replicas=3),
        status=SimpleNamespace(ready_replicas=0, available_replicas=0, conditions=None),
    )
    conn = MagicMock(name="conn")
    conn.apps.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=[dep])
    conn.apps.list_stateful_set_for_all_namespaces.return_value = SimpleNamespace(items=[])
    conn.apps.list_daemon_set_for_all_namespaces.return_value = SimpleNamespace(items=[])
    monkeypatch.setattr(diag_tools, "_get_connection", lambda target=None: conn)

    result = diag_tools.workload_readiness_rca()
    assert "error" not in result
    assert result["workloadsAnalyzed"] == 1
    assert result["findings"][0]["signal"] == "under-replicated"
    assert result["findings"][0]["severity"] == "critical"


@pytest.mark.unit
def test_rank_assigns_explicit_worst_first_rank():
    """Findings state their priority explicitly, not implicitly by list order.

    A consumer — notably a smaller local model summarising the result — must not
    have to infer urgency from a finding's position in the list.
    """
    from k8s_aiops.ops import diagnostics as _diag

    ranked = _diag._rank([{"severity": "info"}, {"severity": "critical"}, {"severity": "warning"}])
    assert [f["severity"] for f in ranked] == ["critical", "warning", "info"]
    assert [f["rank"] for f in ranked] == [1, 2, 3]
