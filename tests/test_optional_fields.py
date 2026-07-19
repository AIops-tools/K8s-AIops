"""Absent fields come back as null, not as an empty string.

An empty string reads as "this field exists and is empty"; a missing field is a
different fact. Collapsing the two hides information from any consumer, and a
smaller local model will confidently invent the difference. These tests pin the
contract end-to-end: helper, ops layer, and the CLI rendering that has to cope
with a null.

Also pinned here: the truncation envelope on the limit-bearing reads, so a
capped result announces that there is more rather than looking complete.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from k8s_aiops.cli import app
from k8s_aiops.governance import opt_str

runner = CliRunner()


def _meta(name="x", namespace="default", **kw):
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        creation_timestamp=None,
        labels=kw.get("labels"),
        annotations=kw.get("annotations"),
        owner_references=kw.get("owner_references"),
    )


# ── the helper ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_opt_str_distinguishes_absent_from_empty():
    assert opt_str(None) is None, "absent must stay absent"
    assert opt_str("") == "", "a genuinely empty value is not the same as absent"
    assert opt_str("kube-system", 64) == "kube-system"


@pytest.mark.unit
def test_opt_str_still_sanitizes_and_truncates():
    assert opt_str("a\x00b") == "ab"  # control character stripped
    assert opt_str("abcdef", 3) == "abc"


@pytest.mark.unit
def test_opt_str_accepts_non_string_values():
    assert opt_str(42) == "42"


# ── the ops layer ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_ops_report_absent_fields_as_none():
    """A pod with no phase and no assigned node reports null, not ''."""
    from k8s_aiops.ops import workloads as ops

    pod = SimpleNamespace(
        metadata=_meta("web-0", "prod"),
        spec=SimpleNamespace(node_name=None, containers=[]),
        status=SimpleNamespace(phase=None, container_statuses=None),
    )
    conn = MagicMock()
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])
    row = ops.list_pods(conn)[0]
    assert row["name"] == "web-0"
    assert row["phase"] is None, "an unset phase is absent, not empty"
    assert row["node"] is None, "an unscheduled pod has no node — that is not ''"


@pytest.mark.unit
def test_ops_keep_empty_string_when_source_is_empty():
    """An explicitly empty upstream value is preserved as '' — not turned into null."""
    from k8s_aiops.ops import workloads as ops

    pod = SimpleNamespace(
        metadata=_meta("", "prod"),
        spec=SimpleNamespace(node_name="node-a", containers=[]),
        status=SimpleNamespace(phase="Running", container_statuses=None),
    )
    conn = MagicMock()
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])
    assert ops.list_pods(conn)[0]["name"] == ""


@pytest.mark.unit
def test_ops_never_drop_the_key_itself():
    """Keys are always present; only their value may be null.

    Omitting a key entirely is worse than a null — the consumer cannot tell the
    field was even considered.
    """
    from k8s_aiops.ops import workloads as ops

    pod = SimpleNamespace(
        metadata=SimpleNamespace(name=None, namespace=None, creation_timestamp=None),
        spec=SimpleNamespace(node_name=None, containers=[]),
        status=SimpleNamespace(phase=None, container_statuses=None),
    )
    conn = MagicMock()
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])
    row = ops.list_pods(conn)[0]
    for key in ("name", "namespace", "phase", "ready", "restarts", "node", "age"):
        assert key in row, f"{key} must be present even when the source omitted it"


@pytest.mark.unit
def test_age_of_absent_timestamp_is_none():
    """An object with no creation timestamp has no age — that is not ''."""
    from k8s_aiops.ops._shared import age_of

    assert age_of(None) is None


@pytest.mark.unit
def test_diagnostics_rows_report_absent_fields_as_none():
    """The RCA transform keeps absent absent, and the analysis still runs."""
    from k8s_aiops.ops import diagnostics as ops

    pod = SimpleNamespace(
        metadata=SimpleNamespace(name=None, namespace=None),
        status=SimpleNamespace(phase=None, conditions=None, container_statuses=None),
    )
    row = ops.pod_to_row(pod)
    assert row["name"] is None and row["namespace"] is None and row["phase"] is None
    # A null name must not crash the finding builder or leak "None" as a name.
    result = ops.pod_health_findings([row])
    assert result["podsAnalyzed"] == 1


# ── the CLI ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_renders_rows_with_null_fields(monkeypatch):
    """The table must survive a null field rather than crashing on render."""
    import k8s_aiops.cli.pod as pod_cli

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    pod = SimpleNamespace(
        metadata=_meta("web-0", "prod"),
        spec=SimpleNamespace(node_name=None, containers=[]),
        status=SimpleNamespace(phase=None, container_statuses=None),
    )
    conn.core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[pod])
    monkeypatch.setattr(pod_cli, "get_connection", lambda target=None: (conn, None))

    result = runner.invoke(app, ["pod", "list"])
    assert result.exit_code == 0, result.output
    assert "web-0" in result.output


# ── the truncation envelope ─────────────────────────────────────────────────


def _event(name="web-0"):
    return SimpleNamespace(
        type="Warning",
        reason="FailedScheduling",
        involved_object=SimpleNamespace(kind="Pod", name=name),
        metadata=SimpleNamespace(namespace="prod", creation_timestamp=None),
        message="0/3 nodes are available",
        last_timestamp=None,
    )


@pytest.mark.unit
def test_event_list_envelope_reports_untruncated():
    from k8s_aiops.ops import workloads as ops

    conn = MagicMock()
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(
        items=[_event()]
    )
    result = ops.list_events(conn, limit=5)
    assert result["returned"] == 1
    assert result["limit"] == 5
    assert result["truncated"] is False
    assert len(result["events"]) == 1


@pytest.mark.unit
def test_event_list_truncation_is_measured_not_guessed():
    """One extra row is fetched, so 'truncated' is a fact, not a length coincidence."""
    from k8s_aiops.ops import workloads as ops

    conn = MagicMock()
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(
        items=[_event(f"web-{i}") for i in range(4)]
    )
    result = ops.list_events(conn, limit=3)

    # The API was asked for limit + 1 precisely so truncation can be measured.
    _, kwargs = conn.core.list_event_for_all_namespaces.call_args
    assert kwargs["limit"] == 4

    assert result["truncated"] is True
    assert result["returned"] == 3, "only 'limit' rows are returned to the caller"
    assert result["limit"] == 3
    assert len(result["events"]) == 3


@pytest.mark.unit
def test_event_list_exactly_at_the_limit_is_not_truncated():
    """The classic false positive: len(rows) == limit does NOT mean 'more'."""
    from k8s_aiops.ops import workloads as ops

    conn = MagicMock()
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(
        items=[_event(f"web-{i}") for i in range(3)]
    )
    result = ops.list_events(conn, limit=3)
    assert result["returned"] == 3
    assert result["truncated"] is False


@pytest.mark.unit
def test_cli_events_announces_truncation(monkeypatch):
    import k8s_aiops.cli._root as root_cli

    conn = MagicMock()
    conn.default_namespace.return_value = "default"
    conn.core.list_event_for_all_namespaces.return_value = SimpleNamespace(
        items=[_event(f"web-{i}") for i in range(4)]
    )
    monkeypatch.setattr(
        "k8s_aiops.cli._common.get_connection", lambda target=None: (conn, None)
    )
    assert root_cli  # the command body imports get_connection lazily

    result = runner.invoke(app, ["events", "--limit", "3"])
    assert result.exit_code == 0, result.output
    assert "truncated" in result.output
    assert "--limit" in result.output


@pytest.mark.unit
def test_undo_list_envelope_measures_truncation(monkeypatch):
    from mcp_server.tools import undo as undo_tools

    rows = [
        {
            "undo_id": f"u{i}",
            "ts": "2026-07-18T00:00:00Z",
            "tool": "scale_deployment",
            "undo_tool": "scale_deployment",
            "note": "",
        }
        for i in range(4)
    ]
    captured = {}

    class _Store:
        def list(self, *, status=None, limit=50):
            captured["limit"] = limit
            return rows[:limit]

    monkeypatch.setattr(undo_tools, "get_undo_store", lambda: _Store())
    result = undo_tools.undo_list(limit=3)
    assert captured["limit"] == 4, "one extra row is fetched to measure truncation"
    assert result["returned"] == 3
    assert result["limit"] == 3
    assert result["truncated"] is True
    assert len(result["undos"]) == 3
