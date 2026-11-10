"""
GUI regression tests for final boundary editing, completion state, and saving.

All files and waveform values are synthetic.
No Turbo access or finalization dialogs are required.
"""

from __future__ import annotations

import json

from PyQt5.QtCore import Qt

import adjudication.paths as paths_module

from adjudication.config import ComparisonStatus
from adjudication.paths import get_adjudication_paths
from adjudication.persistence import load_existing_adjudication


def apply_valid_label(window, qtbot) -> None:
    """
    Apply a valid final label through the real sidebar button.
    """
    window.adjudication_cpr_dropdown.setCurrentText("No")
    window.adjudication_rhythm_dropdown.setCurrentText(
        "Normal Heart Rhythm"
    )
    window.adjudication_explanation.setPlainText("")

    assert window.adjudication_apply_btn.isEnabled()
    qtbot.mouseClick(
        window.adjudication_apply_btn,
        Qt.LeftButton,
    )


# =============================================================================
# Boundary insertion and removal
# =============================================================================

def test_add_boundary_splits_final_interval(
    adjudication_window,
    qtbot,
):
    """
    Add Boundary must arm placement and split only the final timeline.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    apply_valid_label(window, qtbot)

    original = comparison.prefilled_intervals[0]
    original_start = original.start
    original_end = original.end
    split_time = original_start + 4.0

    original_source_a = [
        interval.to_dict()
        for interval in comparison.annotator_a_intervals
    ]
    original_source_b = [
        interval.to_dict()
        for interval in comparison.annotator_b_intervals
    ]

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_pending_split_index == 0

    # Exercise the placement callback with an absolute epoch coordinate.
    # Physical scene-to-time click mapping can be tested separately.
    window.place_adjudication_boundary(split_time)

    intervals = comparison.prefilled_intervals

    assert len(intervals) == 2
    assert intervals[0].start == original_start
    assert intervals[0].end == split_time
    assert intervals[1].start == split_time
    assert intervals[1].end == original_end

    assert intervals[0].rhythm_label == "Normal Heart Rhythm"
    assert intervals[1].rhythm_label == "Normal Heart Rhythm"
    assert window.adjudication_pending_split_index is None
    assert window.adjudication_dirty is True

    assert [
        interval.to_dict()
        for interval in comparison.annotator_a_intervals
    ] == original_source_a

    assert [
        interval.to_dict()
        for interval in comparison.annotator_b_intervals
    ] == original_source_b


def test_cancel_add_boundary_preserves_timeline(
    adjudication_window,
    qtbot,
):
    """
    Clicking Cancel Add must leave the final timeline unchanged.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    before = [
        interval.to_dict()
        for interval in comparison.prefilled_intervals
    ]

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_pending_split_index == 0

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_pending_split_index is None

    assert [
        interval.to_dict()
        for interval in comparison.prefilled_intervals
    ] == before


def test_remove_boundary_merges_identical_labels(
    adjudication_window,
    qtbot,
):
    """
    Removing a boundary between identical labels must preserve their label.

    Identical labels avoid the different-label confirmation dialog.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    apply_valid_label(window, qtbot)

    original_start = comparison.prefilled_intervals[0].start
    original_end = comparison.prefilled_intervals[0].end

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )
    window.place_adjudication_boundary(original_start + 4.0)

    assert len(comparison.prefilled_intervals) == 2

    window.select_adjudication_interval(0)

    assert window.adjudication_remove_boundary_btn.isEnabled()

    qtbot.mouseClick(
        window.adjudication_remove_boundary_btn,
        Qt.LeftButton,
    )

    intervals = comparison.prefilled_intervals

    assert len(intervals) == 1
    assert intervals[0].start == original_start
    assert intervals[0].end == original_end
    assert intervals[0].rhythm_label == "Normal Heart Rhythm"


# =============================================================================
# Boundary dragging and resolution
# =============================================================================

def test_boundary_drag_preserves_continuity_and_invalidates_resolution(
    adjudication_window,
    qtbot,
):
    """
    Dragging a final boundary must update both adjacent intervals and return
    affected resolved regions to unresolved.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    apply_valid_label(window, qtbot)

    start = comparison.prefilled_intervals[0].start

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )
    window.place_adjudication_boundary(start + 4.0)

    window.select_adjudication_interval(0)
    qtbot.mouseClick(
        window.adjudication_resolve_btn,
        Qt.LeftButton,
    )

    region = comparison.comparison_regions[0]

    assert region.resolved is True
    assert region.status == ComparisonStatus.RESOLVED_DISAGREEMENT

    line = window.adjudication_boundary_lines[0]
    new_boundary = start + 5.0

    # Exercise the same signal emitted when a user finishes dragging.
    line.setValue(new_boundary)
    line.sigPositionChangeFinished.emit(line)

    intervals = comparison.prefilled_intervals

    assert intervals[0].end == new_boundary
    assert intervals[1].start == new_boundary
    assert intervals[0].end == intervals[1].start

    assert region.resolved is False
    assert region.resolved_at is None
    assert region.status == ComparisonStatus.UNRESOLVED_DISAGREEMENT
    assert window.adjudication_dirty is True


# =============================================================================
# Completed/read-only state
# =============================================================================

def test_completed_state_locks_editing_and_reopen_unlocks(
    adjudication_window,
    qtbot,
):
    """
    Completed state must disable editing; explicit reopening restores it.

    Persistence behavior is tested separately. This test exercises UI state.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    apply_valid_label(window, qtbot)

    start = comparison.prefilled_intervals[0].start

    qtbot.mouseClick(
        window.adjudication_add_boundary_btn,
        Qt.LeftButton,
    )
    window.place_adjudication_boundary(start + 4.0)

    comparison.prefilled_intervals[-1].waveform_complete = True
    comparison.prefilled_intervals[-1].terminal_event_status = (
        "does_not_continue_beyond_waveform"
    )

    window.adjudication_complete = True
    window.adjudication_dirty = False
    window.apply_adjudication_read_only_state()

    # Selecting another interval must not accidentally unlock editing.
    window.select_adjudication_interval(1)

    assert not window.adjudication_cpr_dropdown.isEnabled()
    assert not window.adjudication_apply_btn.isEnabled()
    assert not window.adjudication_save_btn.isEnabled()
    assert not window.adjudication_add_boundary_btn.isEnabled()
    assert window.adjudication_reopen_btn.isEnabled()

    assert all(
        not line.movable
        for line in window.adjudication_boundary_lines
    )

    qtbot.mouseClick(
        window.adjudication_reopen_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_complete is False
    assert window.adjudication_reopened_from_complete is True
    assert window.adjudication_dirty is True
    assert window.adjudication_cpr_dropdown.isEnabled()
    assert window.adjudication_save_btn.isEnabled()
    assert not window.adjudication_reopen_btn.isEnabled()

    assert all(
        not interval.waveform_complete
        for interval in comparison.prefilled_intervals
    )

    assert any(
        line.movable
        for line in window.adjudication_boundary_lines
    )


# =============================================================================
# Actual Save Draft button and dropdown status
# =============================================================================

def test_save_button_writes_draft_and_updates_loaded_record_status(
    adjudication_window,
    qtbot,
    monkeypatch,
):
    """
    The Save Draft button must save the loaded session and update its dropdown
    item without modifying source annotation files.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison
    record = window.adjudication_loaded_record
    reviewer = comparison.adjudicator

    # Allow the synthetic reviewer during this test only.
    monkeypatch.setattr(
        paths_module,
        "ADJUDICATORS",
        [reviewer],
    )

    # Configure dropdowns without firing discovery/reviewer callbacks.
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
        record_dropdown.setEnabled(True)
    finally:
        record_dropdown.blockSignals(blocked)

    window.adjudication_records = [dict(record)]
    window.adjudication_record_status_cache.clear()

    source_bytes = {
        comparison.source_a.path: comparison.source_a.path.read_bytes(),
        comparison.source_b.path: comparison.source_b.path.read_bytes(),
    }

    apply_valid_label(window, qtbot)

    window.adjudication_save_btn.setEnabled(True)

    qtbot.mouseClick(
        window.adjudication_save_btn,
        Qt.LeftButton,
    )

    paths = get_adjudication_paths(
        record_output_path=record["output_path"],
        subject=record["subject"],
        file_tag=record["file_tag"],
        adjudicator=reviewer,
    )

    assert paths.draft_csv.is_file()
    assert paths.state_json.is_file()
    assert not paths.complete_csv.exists()

    state = json.loads(
        paths.state_json.read_text(encoding="utf-8")
    )

    assert state["status"] == "draft"
    assert window.adjudication_dirty is False
    assert record_dropdown.itemText(0).startswith("[Draft]")
    assert "successfully" in window.adjudication_save_status.text()

    restored, navigation = load_existing_adjudication(
        record,
        reviewer,
    )

    assert navigation["complete"] is False
    assert (
        restored.prefilled_intervals[0].rhythm_label
        == "Normal Heart Rhythm"
    )

    for path, original_bytes in source_bytes.items():
        assert path.read_bytes() == original_bytes