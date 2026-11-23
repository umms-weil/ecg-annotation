"""
Regression tests for explicit boundary selection, reversible dragging,
minimum interval duration, drag guides, and automatic Y scaling.

Tests use synthetic fixtures and the real adjudication window.
No network access or modal input is required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pytest

from PyQt5.QtCore import Qt

import adjudication_callbacks as callbacks_module


# =============================================================================
# Helpers
# =============================================================================

def prepare_labeled_timeline(window: Any, qtbot: Any) -> float:
    """Apply a valid label and return the original waveform start."""
    window.select_adjudication_interval(0)

    window.adjudication_cpr_dropdown.setCurrentText("No")
    window.adjudication_rhythm_dropdown.setCurrentText(
        "Normal Heart Rhythm"
    )
    window.adjudication_explanation.clear()

    qtbot.mouseClick(
        window.adjudication_apply_btn,
        Qt.LeftButton,
    )

    return window.adjudication_comparison.prefilled_intervals[0].start


def split_interval(
    window: Any,
    interval_index: int,
    time_value: float,
    qtbot: Any,
) -> None:
    """Split a selected interval using the existing insertion workflow."""
    window.select_adjudication_interval(interval_index)

    assert window.adjudication_add_boundary_btn.isEnabled()

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )
    window.place_adjudication_boundary(time_value)


def find_boundary(window: Any, left_index: int) -> Any:
    """Find a current handle by its left neighboring interval index."""
    return next(
        line
        for line in window.adjudication_boundary_lines
        if line.adjudication_left_interval_index == left_index
    )


def move_boundary(
    window: Any,
    left_index: int,
    time_value: float,
) -> None:
    """
    Move a handle and emit drag completion.

    Handles are recreated after committing, so callers must fetch a new
    reference before the next move.
    """
    line = find_boundary(window, left_index)
    line.setValue(time_value)
    line.sigPositionChangeFinished.emit(line)


# =============================================================================
# Explicit boundary selection/removal
# =============================================================================

def test_removal_targets_selected_boundary_not_selected_interval(
    adjudication_window,
    qtbot,
):
    """
    Select the second boundary and verify only that boundary is removed.
    """
    window = adjudication_window
    start = prepare_labeled_timeline(window, qtbot)
    comparison = window.adjudication_comparison

    source_before = deepcopy(
        [
            interval.to_dict()
            for interval in comparison.annotator_a_intervals
        ]
    )

    split_interval(window, 0, start + 3.0, qtbot)
    split_interval(window, 1, start + 7.0, qtbot)

    assert len(comparison.prefilled_intervals) == 3

    # Select the first interval, then explicitly choose the second boundary.
    window.select_adjudication_interval(0)
    assert not window.adjudication_remove_boundary_btn.isEnabled()

    second_boundary = find_boundary(window, 1)
    second_boundary.boundarySelected.emit(second_boundary)

    assert window.adjudication_selected_boundary_index == 1

    qtbot.mouseClick(
        window.adjudication_remove_boundary_btn,
        Qt.LeftButton,
    )

    intervals = comparison.prefilled_intervals

    assert len(intervals) == 2

    # The first boundary survives; the selected second boundary disappears.
    assert intervals[0].end == start + 3.0
    assert intervals[1].start == start + 3.0
    assert intervals[1].end == start + 10.0

    assert [
        interval.to_dict()
        for interval in comparison.annotator_a_intervals
    ] == source_before


def test_interval_selection_clears_boundary_selection(
    adjudication_window,
    qtbot,
):
    """An ordinary interval selection must clear the removal target."""
    window = adjudication_window
    start = prepare_labeled_timeline(window, qtbot)

    split_interval(window, 0, start + 4.0, qtbot)

    boundary = find_boundary(window, 0)
    boundary.boundarySelected.emit(boundary)

    assert window.adjudication_selected_boundary_index == 0
    assert window.adjudication_remove_boundary_btn.isEnabled()

    window.select_adjudication_interval(1)

    assert window.adjudication_selected_boundary_index is None
    assert not window.adjudication_remove_boundary_btn.isEnabled()


# =============================================================================
# Reversible dragging and minimum duration
# =============================================================================

def test_boundary_drag_is_reversible(
    adjudication_window,
    qtbot,
):
    """A boundary can move right, left, and back to its original location."""
    window = adjudication_window
    start = prepare_labeled_timeline(window, qtbot)

    split_interval(window, 0, start + 4.0, qtbot)

    for relative_position in (6.0, 2.0, 4.0):
        move_boundary(window, 0, start + relative_position)

        intervals = window.adjudication_comparison.prefilled_intervals

        assert intervals[0].end == start + relative_position
        assert intervals[1].start == start + relative_position
        assert intervals[0].duration >= 1.0
        assert intervals[1].duration >= 1.0


def test_drag_cannot_make_either_interval_shorter_than_one_second(
    adjudication_window,
    qtbot,
):
    """Out-of-range handle positions clamp to the fixed one-second limits."""
    window = adjudication_window
    start = prepare_labeled_timeline(window, qtbot)

    split_interval(window, 0, start + 4.0, qtbot)

    move_boundary(window, 0, start + 0.1)

    intervals = window.adjudication_comparison.prefilled_intervals

    assert intervals[0].duration == pytest.approx(1.0)
    assert intervals[1].duration >= 1.0

    move_boundary(window, 0, start + 9.9)

    intervals = window.adjudication_comparison.prefilled_intervals

    assert intervals[1].duration == pytest.approx(1.0)
    assert intervals[0].duration >= 1.0

    # Returning from the limit must remain possible.
    move_boundary(window, 0, start + 4.0)

    assert intervals[0].end == start + 4.0
    assert intervals[1].start == start + 4.0


# =============================================================================
# Temporary waveform drag guides
# =============================================================================

def test_drag_guides_follow_boundary_and_disappear_on_release(
    adjudication_window,
    qtbot,
):
    """Drag guides update without altering final data until release."""
    window = adjudication_window
    start = prepare_labeled_timeline(window, qtbot)

    split_interval(window, 0, start + 4.0, qtbot)

    line = find_boundary(window, 0)
    new_position = start + 5.0

    line.setValue(new_position)
    line.sigDragged.emit(line)

    guides = list(window.adjudication_boundary_drag_guides)

    assert len(guides) == len(window.adjudication_waveform_plots)
    assert all(
        guide.value() == new_position
        for _plot, guide in guides
    )

    # The preview does not commit interval changes.
    assert (
        window.adjudication_comparison.prefilled_intervals[0].end
        == start + 4.0
    )

    line.sigPositionChangeFinished.emit(line)

    assert (
        window.adjudication_comparison.prefilled_intervals[0].end
        == new_position
    )
    assert window.adjudication_boundary_drag_guides == []
    assert all(
        guide.scene() is None
        for _plot, guide in guides
    )


# =============================================================================
# Automatic Y scaling
# =============================================================================

def test_manual_y_adjustment_disables_only_its_row(
    adjudication_window,
    qtbot,
):
    """Manual Y scaling turns Auto-Y off for that row, not other rows."""
    window = adjudication_window

    assert all(window.adjudication_auto_y_enabled)

    qtbot.mouseClick(
        window.adjudication_y_controls[0]["Y-IN"],
        Qt.LeftButton,
    )

    assert window.adjudication_auto_y_enabled[0] is False
    assert all(window.adjudication_auto_y_enabled[1:])
    assert (
        window.adjudication_y_controls[0]["AUTO-Y"].text()
        == "AUTO OFF"
    )

    qtbot.mouseClick(
        window.adjudication_y_controls[0]["AUTO-Y"],
        Qt.LeftButton,
    )

    assert window.adjudication_auto_y_enabled[0] is True
    assert (
        window.adjudication_y_controls[0]["AUTO-Y"].text()
        == "AUTO ON"
    )


def test_auto_y_pauses_on_large_window_and_resumes_when_zoomed_in(
    adjudication_window,
    monkeypatch,
):
    """Large-window pause preserves the user's automatic-scaling preference."""
    window = adjudication_window

    monkeypatch.setattr(
        callbacks_module,
        "ADJUDICATION_AUTO_Y_MAX_WINDOW_SEC",
        5.0,
    )

    start = window.adjudication_waveform_start
    anchor = window.adjudication_waveform_plots[0]

    anchor.setXRange(start, start + 10.0, padding=0)
    window.adjudication_auto_y_timer.stop()
    window.update_adjudication_auto_y_buttons()

    assert all(window.adjudication_auto_y_enabled)
    assert all(
        controls["AUTO-Y"].text() == "PAUSED"
        for controls in window.adjudication_y_controls
    )

    # A paused autoscale must leave the current Y range unchanged.
    anchor.setYRange(-50.0, 50.0, padding=0)
    before = tuple(anchor.viewRange()[1])

    window.autoscale_adjudication_visible_rows()

    assert tuple(anchor.viewRange()[1]) == before

    anchor.setXRange(start + 2.0, start + 4.0, padding=0)
    window.adjudication_auto_y_timer.stop()
    window.autoscale_adjudication_visible_rows()

    assert all(window.adjudication_auto_y_enabled)
    assert window.adjudication_y_controls[0]["AUTO-Y"].text() == "AUTO ON"

    low, high = anchor.viewRange()[1]

    assert high - low < 10.0


def test_x_navigation_triggers_debounced_auto_y(
    adjudication_window,
    qtbot,
    monkeypatch,
):
    """The actual X-range signal schedules automatic fitting."""
    window = adjudication_window

    monkeypatch.setattr(
        callbacks_module,
        "ADJUDICATION_AUTO_Y_DEBOUNCE_MS",
        20,
    )

    anchor = window.adjudication_waveform_plots[0]
    start = window.adjudication_waveform_start

    window.adjudication_auto_y_timer.stop()
    anchor.setYRange(-100.0, 100.0, padding=0)

    # Navigation should invoke the connected scheduling callback.
    anchor.setXRange(start + 1.0, start + 3.0, padding=0)

    qtbot.waitUntil(
        lambda: (
            anchor.viewRange()[1][1] - anchor.viewRange()[1][0]
        ) < 10.0,
        timeout=2000,
    )

    assert window.adjudication_auto_y_enabled[0] is True

    # Disable Auto-Y and verify later navigation preserves manual scaling.
    window.toggle_adjudication_auto_y(0)
    anchor.setYRange(-30.0, 30.0, padding=0)
    manual_range = np.asarray(anchor.viewRange()[1])

    anchor.setXRange(start + 2.0, start + 4.0, padding=0)

    qtbot.waitUntil(
        lambda: not window.adjudication_auto_y_timer.isActive(),
        timeout=2000,
    )

    assert np.allclose(
        anchor.viewRange()[1],
        manual_range,
        rtol=0.0,
        atol=1e-6,
    )