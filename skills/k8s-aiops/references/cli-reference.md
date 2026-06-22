# k8s-aiops CLI Reference

All commands accept `-t/--target <name>` to select a configured target (a kube
context). Namespaced commands accept `-n/--namespace <ns>`; omit it to use the
target's default namespace (read lists fall back to all-namespaces).

## Pods

```bash
k8s-aiops pod list [-n <ns>] [-t <target>]
k8s-aiops pod get <name> [-n <ns>]
k8s-aiops pod logs <name> [-n <ns>] [--tail N] [-c <container>]
k8s-aiops pod delete <name> [-n <ns>] [--dry-run]    # destructive: double confirm
```

## Deployments

```bash
k8s-aiops deployment list [-n <ns>]
k8s-aiops deployment get <name> [-n <ns>]
k8s-aiops deployment scale <name> <replicas> [-n <ns>]
k8s-aiops deployment restart <name> [-n <ns>]        # rolling restart
k8s-aiops deployment delete <name> [-n <ns>] [--dry-run]   # HIGH RISK: double confirm
```

## Services

```bash
k8s-aiops service list [-n <ns>]
```

## Nodes

```bash
k8s-aiops node list
k8s-aiops node cordon <name> [--dry-run]             # destructive: double confirm
k8s-aiops node uncordon <name>
```

## Namespaces & Events

```bash
k8s-aiops namespace list
k8s-aiops events [-n <ns>]
```

## Diagnostics & MCP

```bash
k8s-aiops doctor [--skip-auth]    # check config + cluster reachability
k8s-aiops mcp                     # start the MCP server over stdio
```

## Flags summary

| Flag | Meaning |
|------|---------|
| `-t, --target` | Target name from `~/.k8s-aiops/config.yaml` |
| `-n, --namespace` | Namespace scope |
| `--tail` | Trailing log lines (pod logs, default 100) |
| `-c, --container` | Container name (pod logs) |
| `--dry-run` | Preview a destructive op without executing |
| `--skip-auth` | Skip the connectivity check in `doctor` |
