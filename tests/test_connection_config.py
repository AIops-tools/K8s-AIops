"""Tests for the connection layer, config loading, and the ops _shared helper.

The kubernetes ``load_kube_config``/client constructors are patched so no real
kubeconfig or cluster is touched. Assertions cover: teaching-message mapping per
HTTP status, ApiException → K8sApiError translation, per-context client reuse,
target selection, config YAML parsing/fallback, and central ApiException
translation in ``_shared.call`` + ``age_of`` formatting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException

# ── translate_api_error / teaching messages ─────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "status,needle",
    [
        (401, "Authentication/authorization failed"),
        (403, "Authentication/authorization failed"),
        (404, "Resource not found"),
        (409, "Conflict"),
        (503, "transient error"),
        (500, "Kubernetes API error"),
    ],
)
def test_translate_api_error_maps_status_to_teaching_message(status, needle):
    from k8s_aiops.connection import K8sApiError, translate_api_error

    exc = ApiException(status=status, reason="boom")
    err = translate_api_error(exc, path="pods/web-1")
    assert isinstance(err, K8sApiError)
    assert err.status_code == status
    assert err.path == "pods/web-1"
    assert needle in str(err)
    assert "pods/web-1" in str(err)


@pytest.mark.unit
def test_translate_api_error_falls_back_to_body_when_no_reason():
    from k8s_aiops.connection import translate_api_error

    exc = ApiException(status=404)
    exc.reason = None
    exc.body = "namespace not found detail"
    err = translate_api_error(exc)
    # path defaults to "the cluster" and body detail is surfaced.
    assert "the cluster" in str(err)
    assert "namespace not found detail" in str(err)


@pytest.mark.unit
def test_k8sapierror_carries_status_and_path():
    from k8s_aiops.connection import K8sApiError

    err = K8sApiError("nope", status_code=418, path="teapots")
    assert err.status_code == 418
    assert err.path == "teapots"
    assert str(err) == "nope"


# ── K8sConnection: client build + reuse + accessors ─────────────────────────


@pytest.fixture
def _patch_k8s_client(monkeypatch):
    """Patch kube config loader + client constructors; clear the module cache."""
    import k8s_aiops.connection as conn_mod

    conn_mod._CONN_APIS.clear()
    monkeypatch.setattr(conn_mod.k8s_config, "load_kube_config", lambda **kw: None)

    sentinel = {}
    for name in (
        "ApiClient", "CoreV1Api", "AppsV1Api", "BatchV1Api", "NetworkingV1Api",
        "StorageV1Api", "CustomObjectsApi", "ApisApi", "VersionApi",
    ):
        sentinel[name] = MagicMock(name=name, return_value=SimpleNamespace(_api=name))
        monkeypatch.setattr(conn_mod.k8s_client, name, sentinel[name])
    yield conn_mod
    conn_mod._CONN_APIS.clear()


@pytest.mark.unit
def test_connection_exposes_all_typed_apis(_patch_k8s_client):
    from k8s_aiops.config import TargetConfig
    from k8s_aiops.connection import K8sConnection

    target = TargetConfig(name="prod", context="prod-eks", namespace="payments")
    conn = K8sConnection(target)
    for accessor in ("core", "apps", "batch", "networking", "storage", "custom", "apis", "version"):
        assert getattr(conn, accessor) is not None
    assert conn.default_namespace() == "payments"
    assert conn.target is target


@pytest.mark.unit
def test_connection_default_namespace_defaults_to_default(_patch_k8s_client):
    from k8s_aiops.config import TargetConfig
    from k8s_aiops.connection import K8sConnection

    conn = K8sConnection(TargetConfig(name="lab"))
    assert conn.default_namespace() == "default"


@pytest.mark.unit
def test_connection_reuses_apis_per_context_key(_patch_k8s_client):
    from k8s_aiops.config import TargetConfig
    from k8s_aiops.connection import K8sConnection

    t1 = TargetConfig(name="a", context="ctx")
    t2 = TargetConfig(name="b", context="ctx")  # same context_key
    c1 = K8sConnection(t1)
    c2 = K8sConnection(t2)
    # Same context ⇒ same underlying api dict (client reuse).
    assert c1.core is c2.core
    # ApiClient constructor invoked once, not twice.
    assert _patch_k8s_client.k8s_client.ApiClient.call_count == 1


@pytest.mark.unit
def test_connection_build_failure_raises_teaching_error(monkeypatch):
    from kubernetes.config.config_exception import ConfigException

    import k8s_aiops.connection as conn_mod
    from k8s_aiops.config import TargetConfig
    from k8s_aiops.connection import K8sApiError

    conn_mod._CONN_APIS.clear()

    def _boom(**kw):
        raise ConfigException("no such context")

    monkeypatch.setattr(conn_mod.k8s_config, "load_kube_config", _boom)
    with pytest.raises(K8sApiError, match="Could not load kubeconfig"):
        conn_mod.K8sConnection(TargetConfig(name="x", context="ghost"))


# ── ConnectionManager ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_connection_manager_selects_and_caches(_patch_k8s_client):
    from k8s_aiops.config import AppConfig, TargetConfig
    from k8s_aiops.connection import ConnectionManager

    cfg = AppConfig(
        targets=(
            TargetConfig(name="prod", context="prod-eks"),
            TargetConfig(name="lab", context="k3s"),
        )
    )
    mgr = ConnectionManager(cfg)
    assert mgr.list_targets() == ["prod", "lab"]
    default_conn = mgr.connect()  # first target
    same = mgr.connect("prod")
    assert default_conn is same  # cached by name
    assert mgr.list_connected() == ["prod"]
    lab = mgr.connect("lab")
    assert lab is not default_conn
    assert set(mgr.list_connected()) == {"prod", "lab"}


@pytest.mark.unit
def test_connection_manager_unknown_target_raises(_patch_k8s_client):
    from k8s_aiops.config import AppConfig, TargetConfig
    from k8s_aiops.connection import ConnectionManager

    mgr = ConnectionManager(AppConfig(targets=(TargetConfig(name="prod"),)))
    with pytest.raises(KeyError, match="ghost"):
        mgr.connect("ghost")


# ── config.py: load_config / TargetConfig / AppConfig ───────────────────────


@pytest.mark.unit
def test_load_config_missing_file_yields_implicit_default(tmp_path):
    from k8s_aiops.config import load_config

    cfg = load_config(tmp_path / "does-not-exist.yaml")
    assert len(cfg.targets) == 1
    assert cfg.targets[0].name == "default"


@pytest.mark.unit
def test_load_config_parses_targets(tmp_path):
    from k8s_aiops.config import load_config

    p = tmp_path / "config.yaml"
    p.write_text(
        "targets:\n"
        "  - name: prod\n"
        "    context: prod-eks\n"
        "    namespace: payments\n"
        "    kubeconfig: /tmp/kc\n"
        "  - name: lab\n"
        "    context: k3s\n"
    )
    cfg = load_config(p)
    assert [t.name for t in cfg.targets] == ["prod", "lab"]
    prod = cfg.get_target("prod")
    assert prod.context == "prod-eks"
    assert prod.namespace == "payments"
    assert prod.kubeconfig == "/tmp/kc"


@pytest.mark.unit
def test_load_config_empty_targets_falls_back_to_default(tmp_path):
    from k8s_aiops.config import load_config

    p = tmp_path / "config.yaml"
    p.write_text("targets: []\n")
    cfg = load_config(p)
    assert cfg.targets[0].name == "default"


@pytest.mark.unit
def test_appconfig_default_target_empty_raises():
    from k8s_aiops.config import AppConfig

    with pytest.raises(ValueError, match="No targets configured"):
        _ = AppConfig(targets=()).default_target


@pytest.mark.unit
def test_appconfig_get_target_lists_available_on_miss():
    from k8s_aiops.config import AppConfig, TargetConfig

    cfg = AppConfig(targets=(TargetConfig(name="prod"), TargetConfig(name="lab")))
    with pytest.raises(KeyError) as ei:
        cfg.get_target("ghost")
    assert "prod" in str(ei.value) and "lab" in str(ei.value)


@pytest.mark.unit
def test_target_context_key_is_stable_and_distinct():
    from k8s_aiops.config import TargetConfig

    a = TargetConfig(name="a", context="ctx", kubeconfig="/kc")
    b = TargetConfig(name="b", context="ctx", kubeconfig="/kc")
    c = TargetConfig(name="c", context="other")
    assert a.context_key == b.context_key
    assert a.context_key != c.context_key
    assert TargetConfig(name="d").context_key == "~/.kube/config::current"


# ── ops/_shared: call() translation + age_of ────────────────────────────────


@pytest.mark.unit
def test_shared_call_applies_default_timeout_and_returns():
    from k8s_aiops.ops._shared import call

    fn = MagicMock(return_value="ok")
    result = call(fn, "arg", path="pods")
    assert result == "ok"
    _, kwargs = fn.call_args
    assert kwargs["_request_timeout"] == 30


@pytest.mark.unit
def test_shared_call_respects_explicit_timeout():
    from k8s_aiops.ops._shared import call

    fn = MagicMock(return_value="ok")
    call(fn, _request_timeout=5)
    assert fn.call_args.kwargs["_request_timeout"] == 5


@pytest.mark.unit
def test_shared_call_translates_apiexception():
    from k8s_aiops.connection import K8sApiError
    from k8s_aiops.ops._shared import call

    def _boom(**kw):
        raise ApiException(status=404, reason="Not Found")

    with pytest.raises(K8sApiError) as ei:
        call(_boom, path="pods/web-1")
    assert ei.value.status_code == 404
    assert "pods/web-1" in str(ei.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "delta,suffix",
    [
        (timedelta(seconds=10), "s"),
        (timedelta(minutes=5), "m"),
        (timedelta(hours=3), "h"),
        (timedelta(days=2), "d"),
    ],
)
def test_age_of_formats_deltas(delta, suffix):
    from k8s_aiops.ops._shared import age_of

    ts = datetime.now(UTC) - delta
    assert age_of(ts).endswith(suffix)


@pytest.mark.unit
def test_age_of_parses_iso_string_with_z():
    from k8s_aiops.ops._shared import age_of

    ts = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert age_of(ts).endswith("h")


@pytest.mark.unit
def test_age_of_empty_and_invalid_return_blank():
    from k8s_aiops.ops._shared import age_of

    assert age_of(None) == ""
    assert age_of("not-a-timestamp") == ""
