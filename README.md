<!-- mcp-name: io.github.AIops-tools/k8s-aiops -->
# k8s-aiops (preview)

> **Disclaimer**: This is a community-maintained open-source project and is **not
> affiliated with, endorsed by, or sponsored by the Cloud Native Computing
> Foundation, the Kubernetes project, or k3s/Rancher.** "Kubernetes" and "k3s" are
> trademarks of their respective owners. Source code is publicly auditable at
> [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops) under
> the MIT license.

Governed Kubernetes operations for AI agents — **51 MCP tools**, every one wrapped
with the bundled `@governed_tool` harness: a local unified audit log under
`~/.k8s-aiops/`, policy engine, token/runaway budget guard, undo-token recording, and
graduated-autonomy risk tiers. Coverage spans pods, deployments, statefulsets,
daemonsets, replicasets, jobs/cronjobs, services, ingresses, endpoints,
configmaps, secrets (names/keys only), PVCs/PVs/storageclasses, nodes, namespaces,
events, rollouts (status/history/undo/pause/resume/set-image), pod/node describe,
pod/node top, and a cluster health summary.

> **Standalone**: the governance harness is bundled in the package
> (`k8s_aiops.governance`) — k8s-aiops has no external skill-family dependency.
> Preview: common cluster operations, not yet exhaustive.

## What works

Any cluster a kubeconfig can reach: standard Kubernetes, **k3s**, **EKS**, **GKE**,
**AKS**, kind, minikube. Authentication (client certs, tokens, EKS/GKE/AKS exec
plugins) is delegated entirely to the kubeconfig.

## Quick Start

```bash
uv tool install k8s-aiops

# Friendly onboarding wizard — registers your kube contexts as named targets:
k8s-aiops init

# Or skip it — uses your current kube-context out of the box:
k8s-aiops doctor
k8s-aiops pod list
k8s-aiops deployment list -n default
```

To define named targets (multiple clusters/contexts), create
`~/.k8s-aiops/config.yaml`:

```yaml
targets:
  - name: prod          # used as -t prod
    context: prod-eks   # a context in your kubeconfig (omit for current-context)
    namespace: default  # optional default namespace
    # kubeconfig: /path/to/alt/kubeconfig   # optional explicit path
  - name: lab
    context: k3s-lab
```

No secrets live in this file — credentials come from the kubeconfig.

## MCP

```jsonc
{
  "command": "k8s-aiops",
  "args": ["mcp"],
  "env": { "K8S_AIOPS_CONFIG": "~/.k8s-aiops/config.yaml" }
}
```

## Audit & Safety

- Every tool call is logged to `~/.k8s-aiops/audit.db` (local SQLite; relocate with
  `K8S_AIOPS_HOME`).
- Reversible writes record an inverse undo descriptor (`scale_deployment` →
  scale-back to previous; `cordon_node` ↔ `uncordon_node`).
- `delete_deployment` is `risk_level=high`; CLI destructive commands require double
  confirmation and support `--dry-run`.
- All API text passes through `sanitize()` (output hygiene: control/format-char
  stripping + truncation).

See `skills/k8s-aiops/SKILL.md` and `SECURITY.md` for details.

## Secrets

k8s-aiops deliberately has **no encrypted secret store** (no `secrets.enc`, no
`secret` CLI): authentication is delegated entirely to your kubeconfig — client
certificates, bearer tokens, or exec plugins (EKS/GKE/AKS) — and the tool never
handles or stores cluster credentials itself. This is a documented exception to
the AIops-tools line-wide encrypted-secret-store pattern.

## Companion Skills

| If you want… | Use |
|--------------|-----|
| Kubernetes pods / deployments / nodes | **k8s-aiops** (this) |
| Hypervisor VM lifecycle | a hypervisor ops skill |
| Backup & restore | a backup ops skill |

## Contributing & feature requests

This is a preview — coverage is intentionally focused. **Missing a device, action, or feature you need?** Open an issue or pull request at [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops/issues) — feature requests, contributions, and comments are all welcome.

## License

MIT — [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops)
