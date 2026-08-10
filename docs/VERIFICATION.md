# Live verification status

This document records what has and has not been validated against a real
Kubernetes cluster, so the maturity claim is auditable rather than a vibe.

## Already live-verified ✅

`k8s-aiops` was exercised end-to-end against a **real kind cluster (v1.36)** on
2026-07-16. What was checked:

- Connectivity via `k8s-aiops doctor` against a live API server.
- Three classes of pod-failure root-cause analysis against deliberately broken
  workloads.
- A governed write with a real inverse: scaling a Deployment recorded
  `previous_replicas` and the recorded undo restored the prior replica count.
- CLI writes routing through the governed path (audit rows actually landed).

## Not yet live-verified ⚠️

- ~~The **diagnostics/RCA tools added in this release** (`pod_health_rca`,
  `workload_readiness_rca`) are unit-tested against synthetic pod/workload rows
  but have not been re-run against a live cluster.~~ **Both closed 2026-08-10
  against a real kind cluster (Kubernetes v1.34.0)** carrying deliberately
  seeded faults — a CrashLoopBackOff deployment scaled to 2, an
  ImagePullBackOff, a Pending pod requesting 64 CPU / 200Gi, and a healthy
  control.
  - `pod_health_rca` classified all four correctly over 6 pods, worst-first
    with explicit ranks, and did **not** flag the healthy pod: image-pull
    failure and CrashLoopBackOff as `critical` (with real restart counts),
    unschedulable as `warning`.
  - `workload_readiness_rca` flagged `badimage` 0/1 and `crasher` 0/2 as
    under-replicated and left the two 1/1 deployments alone. Its **rollout-stuck
    branch** was then exercised for real by shrinking `progressDeadlineSeconds`
    until the stuck ReplicaSet produced a genuine
    `Progressing=False (ProgressDeadlineExceeded)` — reported as `critical`.
  - **A real defect surfaced**: the unschedulable finding reported only the
    condition's *reason* ("Unschedulable") and dropped its *message* — the part
    that actually answers the question ("0/1 nodes are available: 1 Insufficient
    cpu, 1 Insufficient memory"). The finding told the operator to go run
    `kubectl describe` for a fact the tool already held, which an agent with no
    shell cannot do at all. The scheduler's message is now carried in both
    `detail` and `cause`, with the bare category kept as the fallback when the
    server supplies no message.
- Managed control planes (EKS / GKE / AKS) — only kind and k3s-shaped clusters
  have been touched. Cloud-specific API differences are unexercised.

## What the mock suite guarantees

Every module imports; the CLI builds; every MCP tool carries the
`@governed_tool` harness marker; write tools record the correct inverse undo
descriptor against a mocked client; RCA heuristics are unit-tested against
synthetic telemetry. It does **not** prove field shapes match every real API
server version.

## Checklist to (re)verify against a live cluster

Use a throwaway namespace. Never verify against production workloads.

```bash
uv tool install k8s-aiops
k8s-aiops doctor
```

### 1. Connectivity
- [ ] `k8s-aiops doctor` → green against the target kubeconfig context.

### 2. Reads return real, well-shaped data
- [ ] Workload/pod listing matches `kubectl get` for the same namespace.
- [ ] `k8s-aiops diagnose pod-health` → deliberately break a pod
      (bad image → `ImagePullBackOff`; a crashing command → `CrashLoopBackOff`;
      a tiny memory limit → `OOMKilled`) and confirm each is flagged with the
      correct reason and restart count.
- [ ] `k8s-aiops diagnose workload-readiness` → scale a Deployment beyond
      schedulable capacity and confirm ready<desired is reported.

### 3. A reversible write + its undo
- [ ] Scale a Deployment; confirm the result carries an `_undo_id` and an audit
      row lands in the audit DB.
- [ ] `k8s-aiops undo apply <id>` → the **prior** replica count is restored
      (proves undo captured pre-state rather than guessing).

### 4. Governance records (it does not gate)
- [ ] A `high`-risk op (e.g. `delete_deployment`) with no approver set runs to
      completion — the skill authorizes nothing — and lands an audit row tagged
      `risk_tier=review`. There is no read-only switch, policy file, or approval
      gate to test.
- [ ] A tight poll loop trips the runaway budget guard (a safety backstop, not
      authorization).

### 5. Cleanup
- [ ] Delete the test namespace; confirm the delete is audited.

## Criteria to claim full live verification

Every box above ticked against a recorded Kubernetes version, any field-shape
mismatch fixed and covered by a test, and the result written up with the date
and version. Until the RCA tools are re-run live, this document must keep the
"not yet live-verified" section accurate.
