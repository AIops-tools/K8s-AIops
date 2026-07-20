"""Connection management for the Kubernetes API.

Thin wrapper over the official ``kubernetes`` Python client with per-context
client reuse. A "target" selects a kube context from a kubeconfig
(``KUBECONFIG`` env or ``~/.kube/config``); credentials live in the kubeconfig
(client certs, tokens, or exec plugins for EKS/GKE/AKS) — we never handle them
directly.

Per-connection metadata (the typed Api objects) is kept in a module-level dict
keyed by the target's context key rather than set as an attribute on any client
object. Third-party SDK proxy objects must not be monkey-patched (same
discipline as the pyVmomi 8.x ManagedObject lesson); we apply it pre-emptively.

All ``ApiException``s are translated centrally into ``K8sApiError`` with a
teaching message — REST-wrapper skills should translate API errors at the
connection layer from the first version, not let users hit raw tracebacks.

``credential_namespace()`` reads (never calls the cluster for) the one fact a
write guard needs about our own identity: whether this target's credential is a
ServiceAccount token, and if so which namespace that ServiceAccount lives in.
Deleting that namespace would revoke the credential mid-flight, so
``ops.namespaces`` refuses it.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import yaml
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from k8s_aiops.config import AppConfig, TargetConfig, load_config

# A ServiceAccount's identity is 'system:serviceaccount:<namespace>:<name>'.
_SA_SUB_PREFIX = "system:serviceaccount:"

# Side-stored typed Api objects, keyed by target.context_key. See docstring.
_CONN_APIS: dict[str, dict[str, Any]] = {}


class K8sApiError(Exception):
    """A Kubernetes API call failed; carries a teaching message + status code."""

    def __init__(self, message: str, *, status_code: int | None = None, path: str = "") -> None:
        self.status_code = status_code
        self.path = path
        super().__init__(message)


def _teaching_message(status: int | None, path: str, reason: str) -> str:
    """Map a Kubernetes API status to an actionable, teaching error message."""
    snippet = (reason or "").strip()[:200]
    if status in (401, 403):
        return (
            f"Authentication/authorization failed ({status}) on {path}. "
            f"Check the kubeconfig context and the account's RBAC roles "
            f"(run 'kubectl auth can-i ...'). {snippet}"
        )
    if status == 404:
        return (
            f"Resource not found (404) on {path}. The name/namespace may be "
            f"wrong or the object was deleted — list the parent collection "
            f"first to get a current name. {snippet}"
        )
    if status == 409:
        return (
            f"Conflict (409) on {path}. The object changed concurrently or "
            f"already exists; re-read it and retry. {snippet}"
        )
    if status in (502, 503, 504):
        return (
            f"Kubernetes API server transient error ({status}) on {path}. The "
            f"apiserver may be busy or starting; retry shortly. {snippet}"
        )
    return f"Kubernetes API error ({status}) on {path}. {snippet}"


def translate_api_error(exc: ApiException, path: str = "") -> K8sApiError:
    """Convert a ``kubernetes`` ApiException into a teaching ``K8sApiError``."""
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", "") or ""
    body = getattr(exc, "body", "") or ""
    detail = reason if reason else str(body)
    return K8sApiError(
        _teaching_message(status, path or "the cluster", detail),
        status_code=status,
        path=path,
    )


def _kubeconfig_paths(target: TargetConfig) -> list[Path]:
    """The kubeconfig files this target loads, in the client's own precedence order."""
    if target.kubeconfig:
        return [Path(target.kubeconfig).expanduser()]
    env = os.environ.get("KUBECONFIG", "").strip()
    if env:
        return [Path(p).expanduser() for p in env.split(os.pathsep) if p]
    return [Path.home() / ".kube" / "config"]


def _service_account_namespace(token: str) -> str | None:
    """The namespace of the ServiceAccount a JWT belongs to, or None if it is not one.

    The signature is deliberately NOT verified. This reads our *own* credential to
    learn where it lives; it does not authenticate anybody, so there is nothing to
    verify against and no trust decision resting on the result — the only thing it
    can do is make a write refuse itself.

    Returns None for an opaque/static bearer token: those are not namespace-bound,
    so no namespace deletion can revoke them.
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    body = parts[1]
    claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    sub = claims.get("sub")
    if isinstance(sub, str) and sub.startswith(_SA_SUB_PREFIX):
        namespace = sub[len(_SA_SUB_PREFIX) :].split(":", 1)[0]
        if namespace:
            return namespace
    legacy = claims.get("kubernetes.io/serviceaccount/namespace")  # pre-1.21 tokens
    if isinstance(legacy, str) and legacy:
        return legacy
    bound = claims.get("kubernetes.io")  # projected/bound tokens
    if isinstance(bound, dict) and isinstance(bound.get("namespace"), str):
        return bound["namespace"] or None
    return None


def _context_user(doc: dict, context_name: str | None) -> dict | None:
    """The ``users:`` entry backing a kubeconfig context (or the current-context)."""
    wanted = context_name or doc.get("current-context")
    if not wanted:
        return None
    for ctx in doc.get("contexts") or []:
        if isinstance(ctx, dict) and ctx.get("name") == wanted:
            user_name = (ctx.get("context") or {}).get("user")
            break
    else:
        return None
    if not user_name:
        return None
    for user in doc.get("users") or []:
        if isinstance(user, dict) and user.get("name") == user_name:
            entry = user.get("user")
            return entry if isinstance(entry, dict) else None
    return None


def credential_namespace(target: TargetConfig) -> str | None:
    """The namespace whose ServiceAccount this target authenticates as, or None.

    Reads the kubeconfig off disk only — no cluster call — so a dry run can
    consult it without contacting the apiserver.

    ``None`` means **unknown**: callers must treat it as "cannot guard", never as
    a cleared "not me". Every branch below returns None rather than guessing:

      * client-certificate auth — a cert identity is not namespace-bound, so no
        namespace deletion can revoke it;
      * ``exec`` / ``auth-provider`` credentials (EKS, GKE, AKS) — minted outside
        the cluster, likewise not namespace-bound;
      * an opaque (non-JWT) bearer token, an unreadable/absent kubeconfig, or a
        context that names no user.

    The context's own ``namespace:`` field is deliberately NOT used as evidence.
    It is a default-namespace *preference* for commands, not a statement about
    where the credential lives — keying off it would refuse a cluster-admin's
    perfectly safe delete of whatever namespace they happened to be scoped to.
    """
    try:
        for path in _kubeconfig_paths(target):
            if not path.is_file():
                continue
            with open(path) as fh:
                doc = yaml.safe_load(fh) or {}
            if not isinstance(doc, dict):
                continue
            user = _context_user(doc, target.context)
            if user is None:
                continue  # context lives in a later file of a merged KUBECONFIG
            if "client-certificate" in user or "client-certificate-data" in user:
                return None
            if "exec" in user or "auth-provider" in user:
                return None
            token = user.get("token")
            if isinstance(token, str) and token:
                return _service_account_namespace(token)
            return None
    except Exception:  # noqa: BLE001 — unknown identity, never a false "it is me"
        return None
    return None


class K8sConnection:
    """An authenticated set of typed Api clients for one kube context."""

    def __init__(self, target: TargetConfig) -> None:
        self._target = target
        apis = _CONN_APIS.get(target.context_key)
        if apis is None:
            apis = self._build_apis(target)
            _CONN_APIS[target.context_key] = apis
        self._apis = apis

    @staticmethod
    def _build_apis(target: TargetConfig) -> dict[str, Any]:
        try:
            k8s_config.load_kube_config(
                config_file=target.kubeconfig,
                context=target.context,
            )
        except ConfigException as exc:
            raise K8sApiError(
                f"Could not load kubeconfig (context={target.context or 'current'}): "
                f"{exc}. Check KUBECONFIG / ~/.kube/config and that the context "
                f"exists (run 'kubectl config get-contexts')."
            ) from exc
        api_client = k8s_client.ApiClient()
        return {
            "api_client": api_client,
            "core": k8s_client.CoreV1Api(api_client),
            "apps": k8s_client.AppsV1Api(api_client),
            "batch": k8s_client.BatchV1Api(api_client),
            "networking": k8s_client.NetworkingV1Api(api_client),
            "storage": k8s_client.StorageV1Api(api_client),
            "custom": k8s_client.CustomObjectsApi(api_client),
            "apis": k8s_client.ApisApi(api_client),
            "version": k8s_client.VersionApi(api_client),
        }

    @property
    def target(self) -> TargetConfig:
        return self._target

    @property
    def core(self) -> Any:
        """CoreV1Api — pods, services, nodes, namespaces, events."""
        return self._apis["core"]

    @property
    def apps(self) -> Any:
        """AppsV1Api — deployments, replicasets, statefulsets."""
        return self._apis["apps"]

    @property
    def batch(self) -> Any:
        """BatchV1Api — jobs and cronjobs."""
        return self._apis["batch"]

    @property
    def networking(self) -> Any:
        """NetworkingV1Api — ingresses, network policies."""
        return self._apis["networking"]

    @property
    def storage(self) -> Any:
        """StorageV1Api — storage classes."""
        return self._apis["storage"]

    @property
    def custom(self) -> Any:
        """CustomObjectsApi — metrics.k8s.io (pod/node top) and CRDs."""
        return self._apis["custom"]

    @property
    def apis(self) -> Any:
        """ApisApi — API group discovery (api_resources)."""
        return self._apis["apis"]

    @property
    def version(self) -> Any:
        """VersionApi — cluster /version for liveness checks."""
        return self._apis["version"]

    def default_namespace(self) -> str:
        return self._target.namespace or "default"


class ConnectionManager:
    """Manages connections to multiple Kubernetes targets with client reuse."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._connections: dict[str, K8sConnection] = {}

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> ConnectionManager:
        cfg = config or load_config()
        return cls(cfg)

    def target_config(self, target_name: str | None = None) -> TargetConfig:
        """Resolve a target by name (or the default) WITHOUT building any API client.

        Write guards need the kubeconfig identity before deciding whether an
        operation may proceed, including on the dry-run path — which must be able
        to refuse without contacting the apiserver.
        """
        return (
            self._config.get_target(target_name)
            if target_name
            else self._config.default_target
        )

    def connect(self, target_name: str | None = None) -> K8sConnection:
        """Connect to a target by name, or the default target."""
        target = self.target_config(target_name)
        cached = self._connections.get(target.name)
        if cached is not None:
            return cached
        conn = K8sConnection(target)
        self._connections[target.name] = conn
        return conn

    def list_targets(self) -> list[str]:
        return [t.name for t in self._config.targets]

    def list_connected(self) -> list[str]:
        return list(self._connections.keys())
