# k8s-aiops Capabilities

15 MCP tools (9 read / 6 write). Every tool is wrapped with `@governed_tool`
(audit + policy + budget + risk-tier; undo where a clean inverse exists). Returns
are high-signal summaries — `_get` tools add detail for a single object.

## Read tools

| Tool | Returns | Risk | Typical response tokens |
|------|---------|:----:|:-----------------------:|
| `pod_list` | name, namespace, phase, ready, restarts, node, age | low | ~50–600 |
| `pod_get` | + host_ip, pod_ip, containers | low | ~120 |
| `pod_logs` | trailing log lines (default 100) | low | ~200–2000 |
| `deployment_list` | name, namespace, desired/ready/available, age | low | ~40–400 |
| `deployment_get` | + strategy, images | low | ~120 |
| `service_list` | name, namespace, type, cluster IP, ports | low | ~40–400 |
| `node_list` | name, status, roles, version, schedulable, age | low | ~40–300 |
| `namespace_list` | name, phase, age | low | ~30–150 |
| `event_list` | type, reason, object, namespace, message, age | low | ~100–800 |

## Write tools

| Tool | Effect | Risk | Undo |
|------|--------|:----:|------|
| `scale_deployment` | set replica count | medium | scale back to `previous_replicas` |
| `rollout_restart_deployment` | patch `restartedAt` annotation | medium | none (pods already rolling) |
| `delete_pod` | delete a pod | medium | none (controller recreates) |
| `delete_deployment` | delete deployment + pods | **high** | none |
| `cordon_node` | mark node unschedulable | medium | `uncordon_node` |
| `uncordon_node` | mark node schedulable | medium | `cordon_node` |

## Token-budget notes

- List tools accept a `namespace` filter to keep responses small; events and pod
  listings also accept `limit` / `label_selector` where applicable.
- Prefer `pod_get` / `deployment_get` over re-listing when you already have a name.
- The runaway guard trips on tight poll loops — wait between repeated list calls.

## Design notes / Kubernetes-client assumptions

- Authentication is delegated to the kubeconfig; the skill never touches raw
  credentials (works with client certs, tokens, and EKS/GKE/AKS exec plugins).
- Typed Api clients (`CoreV1Api`, `AppsV1Api`, `VersionApi`) are cached per kube
  context in a module dict — third-party client objects are never monkey-patched.
- `ApiException` is translated centrally at the connection layer into a teaching
  `K8sApiError` (404/403/409/5xx), so agents see actionable messages, not tracebacks.
