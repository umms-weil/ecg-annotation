"""
GUI regression tests for final labels and explicit disagreement resolution.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt

from adjudication.config import ComparisonStatus


def set_valid_final_label(window, rhythm: str) -> None:
    """
    Populate the sidebar with a valid CPR No/rhythm label.

    This helper changes widgets only; Apply Final Label commits the changes.
    """
    window.adjudication_cpr_dropdown.setCurrentText("No")
    window.adjudication_rhythm_dropdown.setCurrentText(rhythm)
    window.adjudication_explanation.setPlainText("")


def test_selection_displays_final_interval_values(
    adjudication_window,
):
    """
    Selecting a labeled interval must populate its sidebar and table values.
    """
    window = adjudication_window
    interval = window.adjudication_comparison.prefilled_intervals[0]

    interval.cpr = "No"
    interval.rhythm_label = "Other"
    interval.rhythm_expl = "Synthetic explanation."

    window.populate_adjudication_table()
    window.select_adjudication_interval(0)

    assert window.adjudication_cpr_dropdown.currentText() == "No"
    assert window.adjudication_rhythm_dropdown.currentText() == "Other"
    assert (
        window.adjudication_explanation.toPlainText()
        == "Synthetic explanation."
    )

    assert window.adjudication_table.item(0, 0).text() == "No"
    assert window.adjudication_table.item(0, 1).text() == "Other"


def test_required_explanation_controls_apply_button(
    adjudication_window,
):
    """
    Other requires an explanation; ordinary rhythms allow optional comments.
    """
    window = adjudication_window

    set_valid_final_label(window, "Other")

    assert window.adjudication_explanation.isEnabled()
    assert not window.adjudication_apply_btn.isEnabled()

    window.adjudication_explanation.setPlainText(
        "Synthetic required explanation."
    )

    assert window.adjudication_apply_btn.isEnabled()

    window.adjudication_rhythm_dropdown.setCurrentText("Bradycardia")
    window.adjudication_explanation.clear()

    assert window.adjudication_explanation.isEnabled()
    assert window.adjudication_apply_btn.isEnabled()


def test_apply_label_does_not_resolve_disagreement(
    adjudication_window,
    qtbot,
):
    """
    Clicking Apply changes the final label but must not mark the region resolved.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    assert len(comparison.unresolved_regions) == 1

    set_valid_final_label(window, "Bradycardia")

    qtbot.mouseClick(
        window.adjudication_apply_btn,
        Qt.LeftButton,
    )

    assert comparison.prefilled_intervals[0].cpr == "No"
    assert comparison.prefilled_intervals[0].rhythm_label == "Bradycardia"
    assert window.adjudication_dirty is True

    region = comparison.comparison_regions[0]

    assert region.resolved is False
    assert region.status == ComparisonStatus.UNRESOLVED_DISAGREEMENT
    assert len(comparison.unresolved_regions) == 1


def test_explicit_resolution_then_edit_returns_to_unresolved(
    adjudication_window,
    qtbot,
):
    """
    Mark Resolved explicitly completes review; a subsequent final edit resets it.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    set_valid_final_label(window, "Bradycardia")
    qtbot.mouseClick(window.adjudication_apply_btn, Qt.LeftButton)

    assert window.adjudication_resolve_btn.isEnabled()

    qtbot.mouseClick(
        window.adjudication_resolve_btn,
        Qt.LeftButton,
    )

    region = comparison.comparison_regions[0]

    assert region.resolved is True
    assert region.resolved_at is not None
    assert region.status == ComparisonStatus.RESOLVED_DISAGREEMENT
    assert comparison.unresolved_regions == []

    # A new final decision requires another explicit review confirmation.
    set_valid_final_label(window, "Normal Heart Rhythm")
    qtbot.mouseClick(window.adjudication_apply_btn, Qt.LeftButton)

    assert region.resolved is False
    assert region.resolved_at is None
    assert region.status == ComparisonStatus.UNRESOLVED_DISAGREEMENT
    assert len(comparison.unresolved_regions) == 1


def test_cpr_unable_requires_explanation(
    adjudication_window,
):
    """
    CPR Unable to Determine disables rhythm and requires explanation.
    """
    window = adjudication_window

    window.adjudication_cpr_dropdown.setCurrentText(
        "Unable to Determine"
    )
    window.adjudication_explanation.clear()

    assert not window.adjudication_rhythm_dropdown.isEnabled()
    assert window.adjudication_rhythm_dropdown.currentText() == ""
    assert window.adjudication_explanation.isEnabled()
    assert not window.adjudication_apply_btn.isEnabled()

    window.adjudication_explanation.setPlainText(
        "Synthetic signal cannot be assessed."
    )

    assert window.adjudication_apply_btn.isEnabled()