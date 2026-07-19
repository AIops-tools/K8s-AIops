"""Read/write operations for batch workloads: Jobs and CronJobs.

Reads return high-signal summaries; ``delete_job`` has no safe inverse (a
recreated job is not the same run). All API-returned text is run through
``sanitize()``.
"""

from __future__ import annotations

from typing import Any

from k8s_aiops.governance import opt_str
from k8s_aiops.ops._shared import age_of, call


def _s(value: Any, limit: int = 128) -> str | None:
    """Sanitize an optional field: absent stays ``None``, never becomes ``""``.

    An empty string reads as "this field exists and is empty"; a missing field
    is a different fact. Collapsing the two hides information from the caller.
    """
    return opt_str(value, limit)


def _job_summary(job: Any) -> dict:
    meta = job.metadata
    status = job.status
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "completions": job.spec.completions,
        "succeeded": (status.succeeded or 0) if status else 0,
        "failed": (status.failed or 0) if status else 0,
        "active": (status.active or 0) if status else 0,
        "age": age_of(meta.creation_timestamp),
    }


def list_jobs(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List jobs (name, namespace, completions, succeeded/failed, age)."""
    if namespace:
        result = call(conn.batch.list_namespaced_job, namespace, path="jobs")
    else:
        result = call(conn.batch.list_job_for_all_namespaces, path="jobs")
    return [_job_summary(j) for j in (result.items or [])]


def get_job(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single job by name."""
    ns = namespace or conn.default_namespace()
    job = call(conn.batch.read_namespaced_job, name, ns, path=f"jobs/{name}")
    summary = _job_summary(job)
    summary["parallelism"] = job.spec.parallelism
    containers = job.spec.template.spec.containers or []
    summary["images"] = [_s(c.image, 200) for c in containers]
    return summary


def _cronjob_summary(cj: Any) -> dict:
    meta = cj.metadata
    status = cj.status
    last = status.last_schedule_time if status else None
    return {
        "name": _s(meta.name),
        "namespace": _s(meta.namespace, 64),
        "schedule": _s(cj.spec.schedule, 64),
        "suspend": bool(cj.spec.suspend),
        "active": len(status.active or []) if status else 0,
        "last_schedule": age_of(last),
        "age": age_of(meta.creation_timestamp),
    }


def list_cronjobs(conn: Any, namespace: str | None = None) -> list[dict]:
    """[READ] List cronjobs (name, namespace, schedule, suspend, active, age)."""
    if namespace:
        result = call(conn.batch.list_namespaced_cron_job, namespace, path="cronjobs")
    else:
        result = call(conn.batch.list_cron_job_for_all_namespaces, path="cronjobs")
    return [_cronjob_summary(c) for c in (result.items or [])]


def get_cronjob(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[READ] Return detail for a single cronjob by name."""
    ns = namespace or conn.default_namespace()
    cj = call(conn.batch.read_namespaced_cron_job, name, ns, path=f"cronjobs/{name}")
    summary = _cronjob_summary(cj)
    summary["concurrency_policy"] = _s(cj.spec.concurrency_policy, 32)
    return summary


def delete_job(conn: Any, name: str, namespace: str | None = None) -> dict:
    """[WRITE] Delete a job and its pods. No undo — a rerun is a new run."""
    ns = namespace or conn.default_namespace()
    call(conn.batch.delete_namespaced_job, name, ns, path=f"jobs/{name}")
    return {"name": _s(name), "namespace": _s(ns, 64), "action": "deleted"}
