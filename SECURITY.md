# Security Policy

## Disclaimer

This is a community-maintained open-source project and is **not affiliated with,
endorsed by, or sponsored by the Cloud Native Computing Foundation, the Kubernetes
project, or k3s/Rancher.** "Kubernetes" and "k3s" are trademarks of their respective
owners. Source code is publicly auditable at
[github.com/AIops-tools/K8s-AIops](https://github.com/AIops-tools/K8s-AIops) under
the MIT license.

## Reporting Vulnerabilities

Report security issues privately to **zhouwei008@gmail.com** or via a GitHub
private security advisory on the repository. Please do not open public issues for
undisclosed vulnerabilities.

## Security Design

### Credential Management

k8s-aiops does **not** store or handle cluster credentials directly. All
authentication is delegated to the kubeconfig (`KUBECONFIG` env or `~/.kube/config`),
which may hold client certificates, bearer tokens, or exec plugins (for EKS/GKE/AKS).
The skill loads a kube context via the official `kubernetes` client and never reads,
logs, or echoes the underlying credentials. The state directory `~/.k8s-aiops` should
be owner-only (`chmod 700`); the skill warns if it is more permissive.

### Destructive Operation Safety

Write operations (scale, rollout restart/undo/pause/resume, set image, delete
pod/deployment/job, create/delete namespace, cordon/uncordon/drain) all pass through
the bundled `@governed_tool` decorator: policy pre-check, token / runaway budget
guard, graduated-autonomy risk-tier gate, and audit logging. The CLI layer
additionally requires double confirmation and supports `--dry-run` for the most
destructive commands (deployment/job/namespace delete, node cordon/drain, rollout
undo). Reversible writes record an inverse undo descriptor — `scale_deployment` /
`scale_statefulset` record a scale-back to the previous replica count;
`set_deployment_image` restores the previous image; `cordon_node` ↔ `uncordon_node`
and `rollout_pause` ↔ `rollout_resume` are mutual inverses; `create_namespace` ↔
`delete_namespace`. `delete_*` and `rollout_undo_deployment` declare no undo.
`risk_level=high`: `delete_deployment`, `delete_job`, `delete_namespace`,
`drain_node`, `rollout_undo_deployment`.

### Secret Confidentiality

`secret_list` returns secret names, types, and key NAMES only — secret VALUES are
never read, returned, or logged, and there is deliberately no tool that returns
secret values. ConfigMap values (non-secret configuration) are returned by
`configmap_get`.

### Least Privilege

Use a kube context bound to a ServiceAccount or user with only the RBAC verbs you
need. Read-only use requires only `get`/`list`/`watch`; the write tools additionally
need `patch`/`delete` on the relevant resources.

### Webhooks / Outbound Network

None. The skill makes no outbound network calls beyond the configured Kubernetes API
server. There are no background services or post-install scripts.

### TLS Verification

TLS verification follows the kubeconfig (`certificate-authority` / `insecure-skip-tls-verify`).
The skill does not weaken it; disable verification only in the kubeconfig itself and
only for self-signed lab clusters.

### Prompt Injection Protection

All text returned from the Kubernetes API (names, log lines, event messages) is run
through `sanitize()` — truncation plus C0/C1 control-character stripping — before
reaching the agent.

### Transitive Dependencies

`kubernetes` (official Python client), `typer`/`rich` (CLI), `pyyaml` (config), and
the MCP SDK. No external skill-family dependency — the governance harness is vendored
under `k8s_aiops.governance`.

## Static Analysis

```bash
uvx bandit -r k8s_aiops/ mcp_server/
```

## Supported Versions

The latest released version (currently 0.1.0, preview) receives security fixes.
