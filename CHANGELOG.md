# Changelog

## v0.4.0 — 2026-07-16

### Fixed
- **`secrets.enc` now follows `K8S_AIOPS_HOME`** (secretstore hardcoded the real
  home directory; config/audit/undo already relocated — found in live verification).
- **Audit fidelity**: failures sanitized into `{"error": ...}` results by the MCP error
  layer are now audited as `status=error` (they previously read as `ok`, hiding failed
  attempts from exception reports), and no undo is recorded for a call that failed.
- **All 15 MCP write tools now accept `dry_run=True` previews** (no client call, no undo recorded for previews).
- CLI `deployment scale`/`restart` gained `--dry-run` + a confirm step.
- Docs: MCP clients spawn servers with a CLEAN environment — set `K8S_AIOPS_HOME`/`K8S_AUDIT_APPROVED_BY`/`KUBECONFIG` in the MCP config's `env` block.

### Tests
- `doctor` and the `init` wizard are now fully covered (previously ~10–20%); plus a
  regression test for the sanitized-failure audit status.

## v0.3.0 — 2026-07-13

Security-hardening release from a line-wide code review.

### Changed (behavior)
- **Secure by default**: with no `rules.yaml`, high/critical operations now require a
  named approver (`K8S_AUDIT_APPROVED_BY`). A fresh install no longer allows
  destructive writes unattended; `init` seeds a starter `rules.yaml` you can edit,
  and an operator-authored rules file is honoured as-is.
- `__version__` is now single-sourced from package metadata (the previous release
  self-reported a stale version string).
- Sanitize docs no longer overstate scope: it strips control/format characters and
  truncates; semantic prompt-injection resistance must come from the consuming agent.

### Fixed
- Kubernetes API calls now carry `_request_timeout=30` (hung apiserver can no longer block the agent indefinitely).
- README documents the deliberate no-encrypted-secret-store exception (kubeconfig-delegated auth).

### Tests
- Governance persistence is now tested against REAL `audit.db`/`undo.db` files
  (write → audit row + inverse undo row with captured prior state).
- The CLI confirmed-write path (dry-run / double-confirm / governed execution) is
  covered end-to-end.
- `pytest-cov` added to the dev dependencies.

## v0.2.1

- Fix: `K8S_AIOPS_HOME` now also relocates `config.yaml` (was hardcoded to `~/.k8s-aiops`).
- Fix: **CLI writes are now audited + undo-recorded** via the governance path — previously only the MCP tools recorded audit/undo; CLI `manage`/`remediate`/etc. writes now go through the same `@governed_tool` layer (they keep their dry-run + double-confirm). CLI write output is now the governed JSON result. No API/tool changes.


All notable changes to **k8s-aiops** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-27

A major capability release: MCP tools expanded from **15 → 51** plus a friendly
onboarding wizard.

### Added
- **Onboarding wizard** — `k8s-aiops init` discovers kube contexts via the
  kubeconfig, lets you register them as named targets with an optional default
  namespace, and writes `~/.k8s-aiops/config.yaml`. Gracefully guides you when no
  kubeconfig is found, and offers to run `doctor` at the end.
- **Controllers** — `statefulset_list/get`, `daemonset_list/get`, `replicaset_list`,
  `scale_statefulset`.
- **Batch** — `job_list/get`, `cronjob_list/get`, `delete_job`.
- **Config** — `configmap_list/get`, `secret_list` (returns names + key **names**
  only; secret values are never read or returned).
- **Storage** — `pvc_list/get`, `pv_list`, `storageclass_list`.
- **Networking** — `ingress_list/get`, `endpoints_list`.
- **Describe** — `pod_describe` (conditions, container states, restart counts,
  recent events), `node_describe` (capacity, allocatable, conditions, taints).
- **Rollouts** — `rollout_status`, `rollout_history`, `rollout_undo_deployment`,
  `rollout_pause`/`rollout_resume`, `set_deployment_image` (captures the previous
  image for an accurate undo token).
- **Metrics** — `pod_top`, `node_top` via `metrics.k8s.io`; when metrics-server is
  absent they return a clear message instead of crashing.
- **Cluster** — `cluster_info` (server version + node/ready/namespace counts),
  `api_resources`.
- **Node/namespace lifecycle** — `drain_node` (cordon + evict, skips DaemonSet and
  mirror pods), `create_namespace`/`delete_namespace`.
- New connection APIs wired in: `BatchV1Api`, `NetworkingV1Api`, `StorageV1Api`,
  `CustomObjectsApi`, `ApisApi`.

### Changed
- `doctor` now nudges toward `k8s-aiops init` when no config exists and verifies
  each target's context resolves in the kubeconfig (reported as status, never a
  traceback).
- Dropped the "SKELETON / preview" label from the CLI help.

### Security
- `secret_list` never reads or returns secret values — only names, types, and key
  names. All new mutating tools run through the governance harness (audit, budget,
  risk-tier, undo) with correct risk tiers (delete/drain/undo = high).

### Notes
- Still validated against mocked Kubernetes clients; verify against a live cluster
  before production use. `pod_top`/`node_top` require metrics-server.

## [0.1.0] — 2026-06-22

Initial preview release: pods, deployments, services, events, nodes, namespaces,
scale, rollout restart, delete (15 MCP tools), with the vendored governance harness.

[0.2.0]: https://github.com/AIops-tools/K8s-AIops/releases/tag/v0.2.0
[0.1.0]: https://github.com/AIops-tools/K8s-AIops/releases/tag/v0.1.0
