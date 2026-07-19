<!-- mcp-name: io.github.AIops-tools/k8s-aiops -->
# k8s-aiops

> **Disclaimer**: This is a community-maintained open-source project and is **not
> affiliated with, endorsed by, or sponsored by the Cloud Native Computing
> Foundation, the Kubernetes project, or k3s/Rancher.** "Kubernetes" and "k3s" are
> trademarks of their respective owners. Source code is publicly auditable at
> [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops) under
> the MIT license.

Governed Kubernetes operations for AI agents — **55 MCP tools**, every one wrapped
with the bundled `@governed_tool` harness: a local unified audit log under
`~/.k8s-aiops/`, policy engine, token/runaway budget guard, undo-token recording, and
graduated-autonomy risk tiers. Coverage spans pods, deployments, statefulsets,
daemonsets, replicasets, jobs/cronjobs, services, ingresses, endpoints,
configmaps, secrets (names/keys only), PVCs/PVs/storageclasses, nodes, namespaces,
events, rollouts (status/history/undo/pause/resume/set-image), pod/node describe,
pod/node top, a cluster health summary, and read-only **diagnostics / RCA**
(pod-health and workload-readiness) that flag the root cause worst-first.

> **Standalone**: the governance harness is bundled in the package
> (`k8s_aiops.governance`) — k8s-aiops has no external skill-family dependency.
> Coverage focuses on common cluster operations and is not yet exhaustive.

> **Verification status**: exercised end-to-end against a live kind cluster (v1.36); the
> diagnostics/RCA tools added in this release are mock-tested only. See
> [docs/VERIFICATION.md](docs/VERIFICATION.md).

## What works

Any cluster a kubeconfig can reach: standard Kubernetes, **k3s**, **EKS**, **GKE**,
**AKS**, kind, minikube. Authentication (client certs, tokens, EKS/GKE/AKS exec
plugins) is delegated entirely to the kubeconfig.

## Security: read-only mode

This tool is meant to be handed to an AI agent, so its safety story is enforced
by the server rather than requested in a prompt:

```bash
export K8S_READ_ONLY=1
```

With that set, the **16 write tools are never registered**. An MCP client
lists **39 tools instead of 55** — the writes are not hidden, not
gated behind a flag, and not merely refused when called. They are absent from
the session. A model cannot invoke a tool it was never offered, and cannot be
argued into one.

That distinction is the whole point. A tool that exists but refuses still invites
retry loops and "I'll describe the call instead" behaviour from smaller models,
and it leaves a reviewer trusting a promise. An absent tool is a fact you can
check: connect, list the tools, and see that the writes are not there.

Enforcement is two layers deep, so the switch cannot be sidestepped by changing
entry point:

| Layer | What it does | Covers |
|---|---|---|
| `@governed_tool` harness | refuses every non-read operation outright | MCP, CLI, and in-process callers |
| MCP registration | write tools are removed from `list_tools()` | anything speaking MCP |

Read operations are unaffected, and every call is still audited to
`~/.k8s-aiops/audit.db`.

> The read/write split is derived from each tool's declared `risk_level`, and a
> test asserts that this never disagrees with the `[READ]`/`[WRITE]` tag in the
> tool's own documentation — so a write can't quietly present itself as a read.

Running a smaller / local model? See
[agent-guardrails.md](skills/k8s-aiops/references/agent-guardrails.md) — it lists
the guardrails this tool now enforces for you (so you don't spend prompt budget
restating them) and gives a ready-made system prompt for what's left.

## Quick Start

```bash
uv tool install k8s-aiops

# Friendly onboarding wizard — registers your kube contexts as named targets:
k8s-aiops init

# Or skip it — uses your current kube-context out of the box:
k8s-aiops doctor
k8s-aiops pod list
k8s-aiops deployment list -n default

# Read-only RCA — worst-first root-cause findings, no changes made:
k8s-aiops diagnose pod-health -n prod
k8s-aiops diagnose workload-readiness -n prod
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

> **Note — MCP servers get a clean environment**: most MCP clients spawn the
> server without your shell's exports, so variables like `K8S_AIOPS_HOME`,
> `K8S_AUDIT_APPROVED_BY`, `K8S_AUDIT_RATIONALE` (and `KUBECONFIG`, if your
> kubeconfig is not at `~/.kube/config`) must be set in the MCP server
> config's `env` block above — values exported only in your terminal may
> never reach the server.

## Audit & Safety

- Every tool call is logged to `~/.k8s-aiops/audit.db` (local SQLite; relocate with
  `K8S_AIOPS_HOME`).
- Reversible writes record an inverse undo descriptor (`scale_deployment` →
  scale-back to previous; `cordon_node` ↔ `uncordon_node`).
- Every MCP write tool takes `dry_run=True` and returns a `{"dryRun": true, ...}`
  preview without touching the cluster (no undo recorded for a preview).
- `delete_deployment` is `risk_level=high`; destructive CLI commands require double
  confirmation, medium-risk ones (`deployment scale`/`restart`) a single
  confirmation, and all write commands support `--dry-run`.
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

Coverage is intentionally focused. **Missing a device, action, or feature you need?** Open an issue or pull request at [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops/issues) — feature requests, contributions, and comments are all welcome.

## License

MIT — [github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops)
