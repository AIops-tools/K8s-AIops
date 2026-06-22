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
"""

from __future__ import annotations

from typing import Any

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from k8s_aiops.config import AppConfig, TargetConfig, load_config

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

    def connect(self, target_name: str | None = None) -> K8sConnection:
        """Connect to a target by name, or the default target."""
        target = (
            self._config.get_target(target_name)
            if target_name
            else self._config.default_target
        )
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
