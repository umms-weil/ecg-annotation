"""
Tests for non-blocking adjudication draft autosave.

Persistence itself is covered by the existing persistence tests.
These tests verify autosave eligibility and failure handling.
"""

from __future__ import annotations

from typing import Any

import pytest


def test_autosave_saves_changed_editable_session(
    adjudication_window,
    monkeypatch,
):
    """Autosave invokes draft saving for eligible changed work."""
    window = adjudication_window
    calls: list[bool] = []

    window.adjudication_dirty = True
    window.adjudication_complete = False

    def successful_save() -> None:
        calls.append(True)
        window.adjudication_dirty = False

    monkeypatch.setattr(
        window,
        "_save_current_adjudication_draft_impl",
        successful_save,
    )

    window.autosave_current_adjudication()

    assert calls == [True]
    assert window.adjudication_dirty is False
    assert window.adjudication_autosave_in_progress is False
    assert "autosaved successfully" in (
        window.adjudication_save_status.text()
    )


@pytest.mark.parametrize(
    "condition",
    ["unchanged", "complete", "pending_boundary", "unapplied_label"],
)
def test_autosave_skips_ineligible_sessions(
    adjudication_window,
    monkeypatch,
    condition,
):
    """Autosave must not commit incomplete interactions or completed work."""
    window = adjudication_window
    calls: list[bool] = []

    window.adjudication_dirty = True
    window.adjudication_complete = False

    if condition == "unchanged":
        window.adjudication_dirty = False

    elif condition == "complete":
        window.adjudication_complete = True

    elif condition == "pending_boundary":
        window.adjudication_pending_split_index = 0

    elif condition == "unapplied_label":
        monkeypatch.setattr(
            window,
            "adjudication_sidebar_has_unapplied_changes",
            lambda: True,
        )

    monkeypatch.setattr(
        window,
        "_save_current_adjudication_draft_impl",
        lambda: calls.append(True),
    )

    window.autosave_current_adjudication()

    assert calls == []
    assert window.adjudication_autosave_in_progress is False


def test_autosave_failure_preserves_edits_without_dialog(
    adjudication_window,
    monkeypatch,
):
    """A failed autosave retains unsaved work and does not open a dialog."""
    window = adjudication_window
    window.adjudication_dirty = True

    def failed_save() -> None:
        raise PermissionError("Synthetic permission failure.")

    def unexpected_dialog(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Autosave must not open a blocking dialog.")

    monkeypatch.setattr(
        window,
        "_save_current_adjudication_draft_impl",
        failed_save,
    )
    monkeypatch.setattr(
        window,
        "show_adjudication_error",
        unexpected_dialog,
    )

    window.autosave_current_adjudication()

    assert window.adjudication_dirty is True
    assert window.adjudication_autosave_in_progress is False
    assert "Autosave failed" in window.adjudication_save_status.text()
    assert "Synthetic permission failure" in (
        window.adjudication_save_status.toolTip()
    )