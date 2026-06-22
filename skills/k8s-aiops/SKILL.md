---
name: k8s-aiops
description: >
  Use this skill whenever the user needs to operate a Kubernetes cluster — list/inspect pods, deployments, services, nodes, namespaces, and events, read pod logs, scale and rollout-restart deployments, delete pods/deployments, and cordon/uncordon nodes. Works with any kubeconfig-reachable cluster (standard Kubernetes, k3s, EKS, GKE, AKS).
  Always use this skill for "list k8s pods", "scale deployment", "kubernetes pod logs", "cordon node", "restart deployment", "k3s", or "kubectl"-style tasks when the context is explicitly Kubernetes / a cluster.
  Do NOT use when the target is not a Kubernetes cluster (hypervisor VM lifecycle, backup products, or cloud-provider consoles are out of scope).
  Preview — common Kubernetes operations with a built-in governance harness (audit, policy, token budget, undo, risk-tiers).
installer:
  kind: uv
  package: k8s-aiops
argument-hint: "[resource name or describe your Kubernetes task]"
allowed-tools:
  - Bash
metadata: {"openclaw":{"requires":{"env":["K8S_AIOPS_CONFIG"],"bins":["k8s-aiops"],"config":["~/.k8s-aiops/config.yaml"]},"optional":{"env":["KUBECONFIG","K8S_AIOPS_HOME"]},"primaryEnv":"K8S_AIOPS_CONFIG","homepage":"https://github.com/AIops-tools/K8s-AIops","emoji":"☸️","os":["macos","linux"]}}
compatibility: >
  Standalone, self-governed Kubernetes operations (preview). The governance harness (audit, policy, token/runaway budget, undo, risk-tiers) is bundled in the package — no external skill-family dependency.
  All write operations are audited to a local SQLite DB under ~/.k8s-aiops/ (relocatable via K8S_AIOPS_HOME).
  Credentials: k8s-aiops handles NO credentials directly — authentication is delegated to the kubeconfig (KUBECONFIG env or ~/.kube/config), which may hold client certs, bearer tokens, or exec plugins (EKS/GKE/AKS). Underlying credentials are never read, logged, or echoed. The state dir ~/.k8s-aiops should be chmod 700.
  Destructive operations (deployment delete, pod delete, node cordon) require double confirmation at the CLI layer and support --dry-run. All write tools pass through the @governed_tool decorator (pre-check + budget guard + audit + risk-tier gate). Reversible writes record an inverse undo descriptor (scale_deployment restores the previous replica count; cordon_node ↔ uncordon_node); delete_* and rollout_restart record none, and delete_deployment is risk_level=high.
  Webhooks: none — no outbound network calls beyond the configured Kubernetes API server.
  TLS: follows the kubeconfig (certificate-authority / insecure-skip-tls-verify); the skill does not weaken it.
  Transitive dependencies: the official kubernetes Python client and the MCP SDK. No post-install scripts or background services.
---

# k8s AIops (preview)

> **Disclaimer**: This is a community-maintained open-source project and is **not affiliated with, endorsed by, or sponsored by the Cloud Native Computing Foundation, the Kubernetes project, or k3s/Rancher.** "Kubernetes" and "k3s" are trademarks of their respective owners. Source code is publicly auditable at [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops) under the MIT license.

Governed Kubernetes operations — **15 MCP tools**, every one wrapped with the bundled `@governed_tool` harness: a local unified audit log under `~/.k8s-aiops/`, policy engine, token/runaway budget guard, undo-token recording, and graduated-autonomy risk tiers. Works with any kubeconfig-reachable cluster (standard Kubernetes, k3s, EKS, GKE, AKS).

> **Standalone**: the governance harness is bundled in the package (`k8s_aiops.governance`) — k8s-aiops has no external skill-family dependency. Preview: common operations, not yet exhaustive.

## What This Skill Does

| Category | Tools | Count | Read or Write |
|----------|-------|:-----:|:-------------:|
| **Pods** | list, get, logs, delete | 4 | 3 read / 1 write |
| **Deployments** | list, get, scale, rollout restart, delete | 5 | 2 read / 3 write |
| **Services** | list | 1 | 1 read |
| **Nodes** | list, cordon, uncordon | 3 | 1 read / 2 write |
| **Namespaces** | list | 1 | 1 read |
| **Events** | list | 1 | 1 read |

## Quick Install

```bash
uv tool install k8s-aiops
k8s-aiops doctor          # uses your current kube-context out of the box
```

## When to Use This Skill

- List/inspect pods, deployments, services, nodes, namespaces and recent events
- Read a pod's recent log lines to diagnose a crash loop
- Scale a deployment up/down, or trigger a rolling restart
- Delete a stuck pod (a controller recreates it) or a deployment
- Cordon a node before maintenance, then uncordon it after

**Do NOT use when** the target is not a Kubernetes cluster (hypervisor VM lifecycle, backup products, or cloud-provider consoles are out of scope for this skill).

## Related Skills — Skill Routing

| If the user wants… | Use |
|--------------------|-----|
| Kubernetes pods / deployments / nodes | **k8s-aiops** (this skill) |
| Hypervisor VM lifecycle (power, snapshot, migrate) | a hypervisor ops skill |
| Backup & restore | a backup ops skill |

## Common Workflows

### Diagnose a crash-looping pod and restart its deployment

1. `k8s-aiops pod list -n prod` → find the pod with high `restarts` / non-Running `phase`
2. `k8s-aiops pod logs <pod> -n prod --tail 200` → read the recent logs for the crash cause
3. `k8s-aiops events -n prod` → check for `FailedScheduling` / image-pull events
4. `k8s-aiops deployment restart <deploy> -n prod` → roll the deployment after fixing the cause
5. **Failure branch**: if logs/events show an RBAC `403`, the kube context lacks the verb — run `kubectl auth can-i get pods -n prod` and switch to a context with adequate RBAC; the skill never retries a denied auth.

### Drain a node for maintenance, safely reversible

1. `k8s-aiops node list` → identify the node and confirm it is `Ready`/schedulable
2. `k8s-aiops node cordon <node> --dry-run` → preview, then `k8s-aiops node cordon <node>` (double confirm) — records an inverse `uncordon_node` undo descriptor
3. After maintenance: `k8s-aiops node uncordon <node>` → re-enable scheduling
4. **Failure branch**: if `doctor` shows the cluster unreachable, fix the kubeconfig context (`kubectl config get-contexts`) before retrying — cordon is never issued against an unauthenticated session.

## Usage Mode

| Scenario | Recommended | Why |
|----------|:-----------:|-----|
| Local/small models (Ollama, Qwen) | **CLI** | fewer tokens than MCP |
| Cloud models (Claude, GPT) | Either | MCP gives structured JSON I/O |
| Automated pipelines | **MCP** | type-safe parameters, audited |

## MCP Tools (15 — 9 read, 6 write)

| Category | Tools | R/W |
|----------|-------|:---:|
| Pods | `pod_list`, `pod_get`, `pod_logs` | Read |
| | `delete_pod` | Write |
| Deployments | `deployment_list`, `deployment_get` | Read |
| | `scale_deployment`, `rollout_restart_deployment`, `delete_deployment` | Write |
| Services | `service_list` | Read |
| Nodes | `node_list` | Read |
| | `cordon_node`, `uncordon_node` | Write |
| Namespaces | `namespace_list` | Read |
| Events | `event_list` | Read |

**Harness features that light up**: write tools with a clean inverse pass an `undo=` lambda so the harness records an inverse descriptor (with `_undo_id`) to the undo store — `scale_deployment` records a scale-back to its returned `previous_replicas`, and `cordon_node` ↔ `uncordon_node` are mutual inverses. `delete_pod`, `delete_deployment`, and `rollout_restart_deployment` declare no undo; `delete_deployment` is tagged `risk_level=high`. All 15 tools are audit-logged under `~/.k8s-aiops/` and pass through the policy pre-check + budget/runaway guard + graduated risk-tier gate. Avoid tight poll loops (re-listing pods every second) — the runaway breaker backs this up.

## CLI Quick Reference

```bash
k8s-aiops pod list [-n <ns>] [-t <target>]
k8s-aiops pod get <name> [-n <ns>]
k8s-aiops pod logs <name> [-n <ns>] [--tail 200] [-c <container>]
k8s-aiops pod delete <name> [-n <ns>] [--dry-run]        # double confirm
k8s-aiops deployment list [-n <ns>]
k8s-aiops deployment get <name> [-n <ns>]
k8s-aiops deployment scale <name> <replicas> [-n <ns>]
k8s-aiops deployment restart <name> [-n <ns>]
k8s-aiops deployment delete <name> [-n <ns>] [--dry-run]  # double confirm
k8s-aiops service list [-n <ns>]
k8s-aiops node list
k8s-aiops node cordon <name> [--dry-run]                  # double confirm
k8s-aiops node uncordon <name>
k8s-aiops namespace list
k8s-aiops events [-n <ns>]
k8s-aiops doctor
k8s-aiops mcp                                             # start MCP server (stdio)
```

See `references/cli-reference.md` for the full command list.

## Troubleshooting

### "Could not load kubeconfig … context not found"
The named context does not exist in your kubeconfig. Run `kubectl config get-contexts` and set the target's `context:` to a listed name (or omit it to use current-context).

### "Authentication/authorization failed (401/403)"
The kube context lacks the RBAC verb for the resource. Check with `kubectl auth can-i <verb> <resource> -n <ns>` and switch to a context/ServiceAccount with adequate roles. For EKS/GKE/AKS, confirm the exec-plugin (aws/gcloud/az CLI) is installed and logged in.

### "Resource not found (404)"
The pod/deployment/node name or namespace is wrong, or the object was deleted. List the parent collection first (`pod list`, `deployment list`, `node list`) to get a current name. Remember most commands default to the `default` namespace unless `-n` is given.

### "Conflict (409)"
The object changed concurrently (or already exists). Re-read it and retry the write.

### Logs are empty or truncated
`pod logs` returns the trailing `--tail` lines (default 100); raise `--tail`. For a multi-container pod, pass `-c <container>` or the API returns an error naming the available containers.

## Audit & Safety

All operations are automatically audited via the bundled `@governed_tool` decorator (`k8s_aiops.governance`):
- Every tool call logged to `~/.k8s-aiops/audit.db` (local SQLite audit DB; relocate with `K8S_AIOPS_HOME`)
- Policy rules enforced via `~/.k8s-aiops/rules.yaml` (deny rules, maintenance windows, risk tiers)
- Budget / runaway guard caps cumulative tool calls and wall-time, and trips on tight poll/retry loops
- Undo store records inverse descriptors for reversible writes (scale → previous replicas; cordon ↔ uncordon)
- Graduated-autonomy risk tiers gate write operations (require a recorded approver for the highest tiers)

The harness is bundled in the package — no external dependency, no manual setup. See `references/setup-guide.md` for security details.

## License

MIT — [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops)
