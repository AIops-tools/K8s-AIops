# Changelog

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
