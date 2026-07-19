"""Flagship signature analyses (RCA) over Kubernetes telemetry — pure analysis.

Every tool in the AIops-tools line ships a *transparent* RCA: each finding is
reported with the measured signal that tripped it (the reason string, the
restart count, the ready/desired ratio) so an operator sees **why** something
was flagged — never a black-box verdict, worst-first.

  1. ``pod_health_findings`` — scan pods and flag CrashLoopBackOff,
     ImagePull failures, OOMKilled (from container lastState), unschedulable
     Pending pods, and high restart counts.
  2. ``workload_readiness_findings`` — scan Deployments / StatefulSets /
     DaemonSets for ready-vs-desired shortfalls and rollout-stuck conditions.

The heuristics are pure functions over *normalized dict rows* (no I/O): the
MCP / CLI layers fetch the live objects and map them with ``pod_to_row`` /
``workload_to_row`` (also pure — object→dict transforms) before analysis. That
keeps the whole module trivially unit-testable without a live cluster.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str

# Thresholds that flip a signal on. Each is surfaced in the finding text next to
# the measured value so the ranking is auditable, not opaque.
RESTART_HIGH = 5

# Container waiting reasons grouped by the class of failure they signal.
_IMAGE_PULL = {"ImagePullBackOff", "ErrImagePull", "ImageInspectError"}
_CONFIG_ERR = {
    "CreateContainerConfigError",
    "CreateContainerError",
    "InvalidImageName",
    "RunContainerError",
}

# Severity ordering used to rank findings most-urgent first.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _int(value: Any) -> int:
    """Coerce a possibly-None replica count to a non-negative int."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _finding(
    severity: str, target: str, signal: str, detail: str, cause: str, action: str
) -> dict:
    """Build one cited finding (immutable dict — callers never mutate it)."""
    return {
        "severity": severity,
        "target": target,
        "signal": signal,
        "detail": detail,
        "cause": cause,
        "action": action,
    }


def _rank(findings: list[dict]) -> list[dict]:
    """Return findings most-urgent first, each carrying its explicit 1-based rank.

    The priority is stated in the payload rather than left implicit in list
    order: a consumer — notably a smaller local model summarising the result —
    should never have to infer urgency from position. Returns new dicts; the
    inputs are not mutated.
    """
    ordered = sorted(findings, key=lambda f: _SEVERITY_RANK.get(f["severity"], 9))
    return [{**finding, "rank": i} for i, finding in enumerate(ordered, 1)]


def _state_reason(state: Any, kind: str) -> str | None:
    """Reason string for a container state phase (waiting/terminated), or None."""
    phase = getattr(state, kind, None) if state is not None else None
    reason = getattr(phase, "reason", None) if phase is not None else None
    return _s(reason, 64) if reason else None


def _unschedulable_reason(conditions: Any) -> str | None:
    """Reason from a PodScheduled=False condition (e.g. 'Unschedulable'), or None."""
    for c in conditions or []:
        if getattr(c, "type", None) == "PodScheduled" and getattr(c, "status", None) != "True":
            return _s(getattr(c, "reason", None) or "NotScheduled", 64)
    return None


def pod_to_row(pod: Any) -> dict:
    """[TRANSFORM] Reduce a V1Pod to a normalized diagnostic row (pure)."""
    status = getattr(pod, "status", None)
    containers = [
        {
            "name": _s(getattr(cs, "name", None), 64),
            "ready": bool(getattr(cs, "ready", False)),
            "restarts": _int(getattr(cs, "restart_count", 0)),
            "waiting": _state_reason(getattr(cs, "state", None), "waiting"),
            "terminated": _state_reason(getattr(cs, "state", None), "terminated"),
            "lastTerminated": _state_reason(getattr(cs, "last_state", None), "terminated"),
        }
        for cs in (getattr(status, "container_statuses", None) or [])
    ]
    return {
        "name": _s(getattr(pod.metadata, "name", None)),
        "namespace": _s(getattr(pod.metadata, "namespace", None), 64),
        "phase": _s(getattr(status, "phase", None), 32),
        "unschedulable": _unschedulable_reason(getattr(status, "conditions", None)),
        "containers": containers,
    }


def _container_findings(where: str, ns: str, name: str, c: dict) -> list[dict]:
    """Findings for a single container row (pure)."""
    cn, restarts = c.get("name") or "?", c.get("restarts") or 0
    waiting, terminated = c.get("waiting"), c.get("terminated")
    out: list[dict] = []
    flagged = False
    if waiting == "CrashLoopBackOff":
        out.append(_finding(
            "critical", where, "CrashLoopBackOff",
            f"container {cn} waiting=CrashLoopBackOff, restarts={restarts}",
            "The container keeps crashing and is restarted with exponential backoff.",
            f"kubectl logs {name} -c {cn} -n {ns} --previous  # find the crash cause"))
        flagged = True
    elif waiting in _IMAGE_PULL:
        out.append(_finding(
            "critical", where, "image pull failure",
            f"container {cn} waiting={waiting}",
            "The image cannot be pulled (bad tag, private registry, or missing pull secret).",
            f"Verify the image ref/tag and imagePullSecrets for {name} in {ns}."))
        flagged = True
    elif waiting in _CONFIG_ERR:
        out.append(_finding(
            "warning", where, "container config error",
            f"container {cn} waiting={waiting}",
            "The container cannot start due to a bad config/secret/volume reference.",
            f"kubectl describe pod {name} -n {ns}  # inspect the referenced config/secret"))
        flagged = True
    if c.get("lastTerminated") == "OOMKilled" or terminated == "OOMKilled":
        out.append(_finding(
            "critical", where, "OOMKilled",
            f"container {cn} last terminated OOMKilled, restarts={restarts}",
            "The container exceeded its memory limit and was killed by the kernel.",
            f"Raise the memory limit for {cn} or fix the leak (kubectl top pod {name} -n {ns})."))
        flagged = True
    if not flagged and restarts >= RESTART_HIGH:
        out.append(_finding(
            "warning", where, "high restart count",
            f"container {cn} restarts={restarts} >= {RESTART_HIGH}",
            "Repeated restarts indicate instability even without an active backoff.",
            f"kubectl logs {name} -c {cn} -n {ns} --previous  # inspect prior exits"))
    return out


def _pod_findings(row: dict) -> list[dict]:
    """Findings for one normalized pod row (pure)."""
    name = row.get("name") or "?"
    ns = row.get("namespace") or "?"
    where = f"{ns}/{name}"
    out: list[dict] = []
    if row.get("unschedulable"):
        out.append(_finding(
            "warning", where, "unschedulable",
            f"pod Pending — PodScheduled=False ({row['unschedulable']})",
            "The scheduler cannot place this pod on any node.",
            f"kubectl describe pod {name} -n {ns}  # check resources/taints/affinity/PVCs"))
    for c in row.get("containers", []):
        out.extend(_container_findings(where, ns, name, c))
    return out


def pod_health_findings(pod_rows: list[dict]) -> dict:
    """[ANALYSIS] Flag CrashLoopBackOff, image-pull failures, OOMKilled,
    unschedulable pods, and high restart counts, worst-first.

    Args:
        pod_rows: normalized rows from ``pod_to_row`` (or hand-built dicts).
    """
    findings: list[dict] = []
    for row in pod_rows:
        findings.extend(_pod_findings(row))
    return {"findings": _rank(findings), "podsAnalyzed": len(pod_rows)}


def workload_to_row(obj: Any, kind: str) -> dict:
    """[TRANSFORM] Reduce a Deployment/StatefulSet/DaemonSet to a row (pure)."""
    status = getattr(obj, "status", None)
    spec = getattr(obj, "spec", None)
    if kind == "DaemonSet":
        desired = _int(getattr(status, "desired_number_scheduled", 0))
        ready = _int(getattr(status, "number_ready", 0))
        available = _int(getattr(status, "number_available", 0))
    else:
        desired = _int(getattr(spec, "replicas", 0))
        ready = _int(getattr(status, "ready_replicas", 0))
        available = _int(getattr(status, "available_replicas", 0))
    conditions = [
        {
            "type": _s(getattr(c, "type", None), 64),
            "status": _s(getattr(c, "status", None), 16),
            "reason": _s(getattr(c, "reason", None), 128),
        }
        for c in (getattr(status, "conditions", None) or [])
    ]
    return {
        "kind": kind,
        "name": _s(getattr(obj.metadata, "name", None)),
        "namespace": _s(getattr(obj.metadata, "namespace", None), 64),
        "desired": desired,
        "ready": ready,
        "available": available,
        "conditions": conditions,
    }


def _workload_findings(row: dict) -> list[dict]:
    """Findings for one normalized workload row (pure)."""
    kind, name, ns = (
        row.get("kind") or "?",
        row.get("name") or "?",
        row.get("namespace") or "?",
    )
    where = f"{ns}/{name}"
    desired, ready = row.get("desired") or 0, row.get("ready") or 0
    out: list[dict] = []
    under = desired > 0 and ready < desired
    if under:
        out.append(_finding(
            "critical" if ready == 0 else "warning", where, "under-replicated",
            f"{kind} {name} ready {ready}/{desired}",
            "No replicas are Ready; the workload is fully down." if ready == 0
            else "Fewer replicas are Ready than desired; availability is degraded.",
            f"kubectl rollout status {kind.lower()}/{name} -n {ns}; "
            f"kubectl get pods -n {ns} to see the failing pods."))
    for cond in row.get("conditions", []):
        ctype, cstatus, reason = cond.get("type"), cond.get("status"), cond.get("reason")
        if ctype == "Progressing" and cstatus == "False":
            out.append(_finding(
                "critical", where, "rollout stuck",
                f"{kind} {name} Progressing=False ({reason})",
                "The rollout is not progressing (often ProgressDeadlineExceeded).",
                f"kubectl rollout status {kind.lower()}/{name} -n {ns}; "
                f"inspect the newest ReplicaSet's pods."))
        elif ctype == "Available" and cstatus == "False" and not under:
            out.append(_finding(
                "warning", where, "unavailable",
                f"{kind} {name} Available=False ({reason})",
                "The workload does not have minimum availability.",
                f"kubectl describe {kind.lower()}/{name} -n {ns}  # why pods are unavailable"))
    return out


def workload_readiness_findings(workload_rows: list[dict]) -> dict:
    """[ANALYSIS] Flag Deployments/StatefulSets/DaemonSets with ready<desired,
    zero-ready outages, and rollout-stuck conditions, worst-first.

    Args:
        workload_rows: normalized rows from ``workload_to_row``.
    """
    findings: list[dict] = []
    for row in workload_rows:
        findings.extend(_workload_findings(row))
    return {"findings": _rank(findings), "workloadsAnalyzed": len(workload_rows)}
