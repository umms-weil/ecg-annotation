"""
GUI tests for adjudication save, resume, and finalization failures.

Failures are injected using monkeypatch. No network storage is accessed.
"""

from __future__ import annotations

from typing import Any

import pytest

from PyQt5.QtCore import Qt

import adjudication_callbacks as callbacks_module

from adjudication.exceptions import SourceFilesChangedError


@pytest.fixture
def captured_errors(
    adjudication_window,
    monkeypatch,
) -> list[tuple[str, str]]:
    """
    Capture error notifications without opening blocking message boxes.

    The actual callbacks still execute their normal error-handling paths.
    """
    errors: list[tuple[str, str]] = []

    def capture_error(title: str, message: str) -> None:
        errors.append((title, message))

    monkeypatch.setattr(
        adjudication_window,
        "show_adjudication_error",
        capture_error,
    )

    return errors


def apply_valid_label(window: Any, qtbot: Any) -> None:
    """Apply a valid label through the existing UI."""
    window.adjudication_cpr_dropdown.setCurrentText("No")
    window.adjudication_rhythm_dropdown.setCurrentText(
        "Normal Heart Rhythm"
    )
    window.adjudication_explanation.clear()

    qtbot.mouseClick(
        window.adjudication_apply_btn,
        Qt.LeftButton,
    )


def configure_selected_record(window: Any) -> None:
    """
    Populate reviewer/record selectors without triggering discovery callbacks.
    """
    record = window.adjudication_loaded_record
    reviewer = window.adjudication_comparison.adjudicator

    reviewer_dropdown = window.adjudicator_dropdown
    blocked = reviewer_dropdown.blockSignals(True)

    try:
        reviewer_dropdown.clear()
        reviewer_dropdown.addItem(reviewer, reviewer)
    finally:
        reviewer_dropdown.blockSignals(blocked)

    record_dropdown = window.adjudication_subject_dropdown
    blocked = record_dropdown.blockSignals(True)

    try:
        record_dropdown.clear()
        record_dropdown.addItem(record["name"], record)
    finally:
        record_dropdown.blockSignals(blocked)


# =============================================================================
# Save failures
# =============================================================================

def test_permission_failure_preserves_unsaved_edits(
    adjudication_window,
    captured_errors,
    monkeypatch,
    qtbot,
):
    """
    A permission failure must retain edits and show a failed-save message.
    """
    window = adjudication_window
    apply_valid_label(window, qtbot)

    original_comparison = window.adjudication_comparison

    def fail_save(*args: Any, **kwargs: Any) -> None:
        raise PermissionError("Synthetic write permission denied.")

    monkeypatch.setattr(
        callbacks_module,
        "save_adjudication_draft",
        fail_save,
    )

    window.adjudication_save_btn.setEnabled(True)

    qtbot.mouseClick(
        window.adjudication_save_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_dirty is True
    assert window.adjudication_comparison is original_comparison

    assert (
        original_comparison.prefilled_intervals[0].rhythm_label
        == "Normal Heart Rhythm"
    )

    assert "Save failed" in window.adjudication_save_status.text()
    assert captured_errors
    assert captured_errors[-1][0] == "Draft Save Failed"
    assert "permission denied" in captured_errors[-1][1]


def test_reopened_save_failure_retains_reopened_state(
    adjudication_window,
    captured_errors,
    monkeypatch,
    qtbot,
):
    """
    Failure of the first reopened draft save must not clear its recovery state.
    """
    window = adjudication_window
    apply_valid_label(window, qtbot)

    window.adjudication_complete = False
    window.adjudication_reopened_from_complete = True
    window.adjudication_dirty = True

    def fail_reopened_save(*args: Any, **kwargs: Any) -> None:
        raise OSError("Synthetic network connection failure.")

    monkeypatch.setattr(
        callbacks_module,
        "save_reopened_adjudication_draft",
        fail_reopened_save,
    )

    window.adjudication_save_btn.setEnabled(True)

    qtbot.mouseClick(
        window.adjudication_save_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_dirty is True
    assert window.adjudication_reopened_from_complete is True
    assert window.adjudication_complete is False

    assert captured_errors
    assert "network connection failure" in captured_errors[-1][1]
    assert "successfully" not in window.adjudication_save_status.text()


# =============================================================================
# Resume failures
# =============================================================================

def test_changed_source_blocks_resume_without_replacing_session(
    adjudication_window,
    captured_errors,
    monkeypatch,
    qtbot,
):
    """
    A changed source must block resume before replacing the displayed session.
    """
    window = adjudication_window
    configure_selected_record(window)

    original_comparison = window.adjudication_comparison
    original_intervals = [
        interval.to_dict()
        for interval in original_comparison.prefilled_intervals
    ]

    def fail_resume(*args: Any, **kwargs: Any) -> None:
        raise SourceFilesChangedError(
            "Synthetic source annotation changed."
        )

    monkeypatch.setattr(
        callbacks_module,
        "load_existing_adjudication",
        fail_resume,
    )

    window.adjudication_resume_btn.setEnabled(True)

    qtbot.mouseClick(
        window.adjudication_resume_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_comparison is original_comparison

    assert [
        interval.to_dict()
        for interval in window.adjudication_comparison.prefilled_intervals
    ] == original_intervals

    assert captured_errors
    assert captured_errors[-1][0] == "Draft Resume Failed"
    assert "source annotation changed" in captured_errors[-1][1]


# =============================================================================
# Finalization rejection
# =============================================================================

def test_unresolved_region_blocks_finalization_before_saving(
    adjudication_window,
    captured_errors,
    monkeypatch,
    qtbot,
):
    """
    Unresolved regions must prevent dialogs and completed-file writing.

    Applying a valid final label alone does not satisfy Mark Resolved.
    """
    window = adjudication_window
    apply_valid_label(window, qtbot)

    save_calls: list[bool] = []

    def unexpected_completed_save(
        *args: Any,
        **kwargs: Any,
    ) -> None:
        save_calls.append(True)
        raise AssertionError(
            "Completed saving must not run with unresolved regions."
        )

    monkeypatch.setattr(
        callbacks_module,
        "save_completed_adjudication",
        unexpected_completed_save,
    )

    window.adjudication_finalize_btn.setEnabled(True)

    qtbot.mouseClick(
        window.adjudication_finalize_btn,
        Qt.LeftButton,
    )

    assert save_calls == []
    assert window.adjudication_complete is False
    assert window.adjudication_dirty is True
    assert window.adjudication_comparison.unresolved_regions

    assert captured_errors
    assert "Mark Resolved" in captured_errors[-1][1]