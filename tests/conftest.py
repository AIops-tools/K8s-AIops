"""Shared fixtures for the k8s-aiops test suite (no live cluster).

The kubernetes client is always mocked (MagicMock/SimpleNamespace); these
fixtures only shape the governance environment the tools run under.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_approver(monkeypatch):
    """Record a synthetic approver globally. It is now only an optional audit
    annotation — no gate depends on it — but setting it keeps the tool-behaviour
    tests' audit rows populated with a representative approved_by value."""
    monkeypatch.setenv("K8S_AUDIT_APPROVED_BY", "pytest")
