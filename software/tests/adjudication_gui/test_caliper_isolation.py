"""
GUI regression tests ensuring temporary calipers do not change final labels.
"""

from __future__ import annotations

from copy import deepcopy

from PyQt5.QtCore import Qt


def test_caliper_adjustment_preserves_adjudication_data(
    adjudication_window,
    qtbot,
):
    """
    Moving a caliper changes only the temporary measurement.

    Final intervals and explicit resolution state must remain unchanged.
    """
    window = adjudication_window
    comparison = window.adjudication_comparison

    original_intervals = deepcopy(
        [interval.to_dict() for interval in comparison.prefilled_intervals]
    )
    original_regions = deepcopy(
        [region.to_dict() for region in comparison.comparison_regions]
    )

    controller = window.adjudication_calipers

    qtbot.mouseClick(controller.toggle_button, Qt.LeftButton)

    assert controller.enabled is True

    qtbot.mouseClick(controller.adjust_button, Qt.LeftButton)

    assert controller.adjusting is True
    assert window.adjudication_caliper_adjust_active is True
    assert not window.adjudication_add_boundary_btn.isEnabled()
    assert not window.adjudication_remove_boundary_btn.isEnabled()

    original_start = controller.start_time

    # Exercise the connected position-change signals without relying on
    # screen-coordinate dragging in a headless environment.
    start_line = next(
        line
        for _plot, role, line in controller.lines
        if role == "start"
    )
    start_line.setValue(original_start + 0.1)

    assert controller.start_time != original_start

    assert [
        interval.to_dict()
        for interval in comparison.prefilled_intervals
    ] == original_intervals

    assert [
        region.to_dict()
        for region in comparison.comparison_regions
    ] == original_regions

    qtbot.mouseClick(controller.adjust_button, Qt.LeftButton)

    assert controller.adjusting is False
    assert window.adjudication_caliper_adjust_active is False