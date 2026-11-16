"""
GUI regression tests for encounter events and temporary calipers.

All waveform values and events are synthetic.
No network access or blocking dialogs are required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pytest
import pyqtgraph as pg

from PyQt5.QtCore import QPointF, Qt


# =============================================================================
# Helpers
# =============================================================================

class SyntheticPlotClick:
    """
    Provide the mouse-event interface used by the plot click handlers.

    Coordinates are generated through the actual plot ViewBox so tests
    exercise scene-to-waveform conversion.
    """

    def __init__(
        self,
        plot: pg.PlotWidget,
        time_value: float,
        signal_value: float = 0.0,
    ) -> None:
        self._scene_position = plot.getViewBox().mapViewToScene(
            QPointF(time_value, signal_value)
        )

    def button(self) -> Any:
        """Return a left mouse button."""
        return Qt.LeftButton

    def scenePos(self) -> QPointF:
        """Return the synthetic scene position."""
        return self._scene_position


def adjudication_snapshot(window: Any) -> dict[str, Any]:
    """
    Snapshot permanent adjudication data for isolation assertions.
    """
    comparison = window.adjudication_comparison

    return deepcopy(
        {
            "intervals": [
                interval.to_dict()
                for interval in comparison.prefilled_intervals
            ],
            "regions": [
                region.to_dict()
                for region in comparison.comparison_regions
            ],
            "dirty": window.adjudication_dirty,
        }
    )


def enable_calipers(window: Any, qtbot: Any) -> Any:
    """
    Enable calipers and disable automatic detection for deterministic tests.
    """
    controller = window.adjudication_calipers

    qtbot.mouseClick(controller.toggle_button, Qt.LeftButton)

    assert controller.enabled

    if controller.auto_enabled:
        qtbot.mouseClick(controller.auto_button, Qt.LeftButton)

    return controller


def manual_source_row(window: Any, controller: Any) -> int:
    """Find a displayed row showing the selected measurement source."""
    source_index = controller.source_dropdown.currentData()

    return next(
        row_index
        for row_index, selector in enumerate(
            window.adjudication_lead_selectors
        )
        if selector.currentData() == source_index
    )


# =============================================================================
# Event graphics
# =============================================================================

def test_event_label_toggle_preserves_vertical_lines(
    adjudication_window,
    qtbot,
):
    """
    Hiding event text must not remove event lines or change adjudication data.
    """
    window = adjudication_window
    before = adjudication_snapshot(window)

    window.adjudication_events = [
        {
            "time": window.adjudication_waveform_start + 5.0,
            "name": "Synthetic pulse check",
            "value": "Synthetic value",
        }
    ]
    window.adjudication_event_labels_visible = True
    window.adjudication_event_labels_btn.setEnabled(True)
    window.draw_adjudication_events()

    labels = [
        item
        for _plot, item in window.adjudication_event_graphics
        if isinstance(item, pg.TextItem)
    ]
    lines = [
        item
        for _plot, item in window.adjudication_event_graphics
        if isinstance(item, pg.InfiniteLine)
    ]

    assert len(labels) == len(window.adjudication_waveform_plots)
    assert len(lines) == len(window.adjudication_waveform_plots)
    assert all(label.isVisible() for label in labels)

    qtbot.mouseClick(
        window.adjudication_event_labels_btn,
        Qt.LeftButton,
    )

    assert not window.adjudication_event_labels_visible
    assert all(not label.isVisible() for label in labels)
    assert all(line.scene() is not None for line in lines)

    qtbot.mouseClick(
        window.adjudication_event_labels_btn,
        Qt.LeftButton,
    )

    assert window.adjudication_event_labels_visible
    assert all(label.isVisible() for label in labels)
    assert adjudication_snapshot(window) == before


def test_event_labels_follow_y_range_without_changing_time(
    adjudication_window,
):
    """
    Y scaling should reposition labels vertically but retain event timestamps.
    """
    window = adjudication_window
    event_time = window.adjudication_waveform_start + 4.0

    window.adjudication_events = [
        {
            "time": event_time,
            "name": "Synthetic event",
            "value": "",
        }
    ]
    window.draw_adjudication_events()

    plot = window.adjudication_waveform_plots[0]
    plot.setYRange(-10.0, 10.0, padding=0)

    # Exercise the positioning callback independently of event-loop timing.
    window.update_adjudication_event_label_positions(0)

    labels = [
        item
        for owner, item in window.adjudication_event_graphics
        if owner is plot and isinstance(item, pg.TextItem)
    ]

    assert len(labels) == 1
    assert labels[0].pos().x() == event_time
    assert -10.0 <= labels[0].pos().y() <= 10.0


def test_lead_switch_restores_events_without_duplicates(
    adjudication_window,
):
    """
    Redrawing a waveform must restore its event graphics without accumulating
    duplicate lines and labels.
    """
    window = adjudication_window

    window.adjudication_events = [
        {
            "time": window.adjudication_waveform_start + 3.0,
            "name": "Synthetic event",
            "value": "",
        }
    ]
    window.draw_adjudication_events()

    expected_count = 2 * len(window.adjudication_waveform_plots)

    assert len(window.adjudication_event_graphics) == expected_count

    window.adjudication_lead_selectors[0].setCurrentIndex(1)
    window.draw_adjudication_waveform(0)

    assert len(window.adjudication_event_graphics) == expected_count
    assert all(
        item.scene() is not None
        for _plot, item in window.adjudication_event_graphics
    )


# =============================================================================
# Manual caliper labeling
# =============================================================================

def test_manual_clicks_calculate_rate_without_changing_adjudication(
    adjudication_window,
    qtbot,
):
    """
    Manual waveform clicks must create temporary dots, calculate rate, and
    leave final intervals and resolution state untouched.
    """
    window = adjudication_window
    before = adjudication_snapshot(window)
    controller = enable_calipers(window, qtbot)

    qtbot.mouseClick(controller.manual_button, Qt.LeftButton)

    assert controller.manual_labeling
    assert controller.mode == "manual"
    assert window.adjudication_caliper_adjust_active

    row = manual_source_row(window, controller)
    plot = window.adjudication_waveform_plots[row]

    # Initial reset creates a centered selection spanning approximately
    # relative seconds 4.25–5.75.
    for relative_time in (4.5, 5.5):
        event = SyntheticPlotClick(
            plot,
            window.adjudication_waveform_start + relative_time,
        )
        window.handle_adjudication_waveform_click(row, event)

    assert len(controller.manual_points) == 2
    assert controller.peak_times.size == 2
    assert controller.rate == pytest.approx(60.0, abs=0.1)
    assert controller.peak_items
    assert adjudication_snapshot(window) == before

    qtbot.mouseClick(controller.manual_button, Qt.LeftButton)

    assert not controller.manual_labeling
    assert not window.adjudication_caliper_adjust_active

    # Leaving labeling mode preserves the temporary measurement.
    assert len(controller.manual_points) == 2
    assert controller.rate == pytest.approx(60.0, abs=0.1)


def test_manual_click_restrictions_duplicate_undo_and_clear(
    adjudication_window,
    qtbot,
):
    """
    Manual dots must respect source/range restrictions and support correction.
    """
    window = adjudication_window
    controller = enable_calipers(window, qtbot)

    qtbot.mouseClick(controller.manual_button, Qt.LeftButton)

    source_row = manual_source_row(window, controller)
    source_plot = window.adjudication_waveform_plots[source_row]

    wrong_row = next(
        index
        for index, selector in enumerate(
            window.adjudication_lead_selectors
        )
        if selector.currentData() != controller.source_dropdown.currentData()
    )

    wrong_source_event = SyntheticPlotClick(
        window.adjudication_waveform_plots[wrong_row],
        window.adjudication_waveform_start + 5.0,
    )
    window.handle_adjudication_waveform_click(
        wrong_row,
        wrong_source_event,
    )

    assert controller.manual_points == []

    outside_event = SyntheticPlotClick(
        source_plot,
        window.adjudication_waveform_start + 1.0,
    )
    window.handle_adjudication_waveform_click(
        source_row,
        outside_event,
    )

    assert controller.manual_points == []

    first_event = SyntheticPlotClick(
        source_plot,
        window.adjudication_waveform_start + 4.5,
    )

    window.handle_adjudication_waveform_click(source_row, first_event)
    window.handle_adjudication_waveform_click(source_row, first_event)

    # Repeated clicks on the same sample must not duplicate a dot.
    assert len(controller.manual_points) == 1

    second_event = SyntheticPlotClick(
        source_plot,
        window.adjudication_waveform_start + 5.5,
    )
    window.handle_adjudication_waveform_click(source_row, second_event)

    assert len(controller.manual_points) == 2
    assert controller.rate is not None

    qtbot.mouseClick(controller.undo_button, Qt.LeftButton)

    assert len(controller.manual_points) == 1
    assert controller.rate is None

    qtbot.mouseClick(controller.clear_dots_button, Qt.LeftButton)

    assert controller.manual_points == []
    assert controller.peak_times.size == 0
    assert controller.peak_items == []
    assert controller.rate is None


def test_source_change_clears_manual_measurement(
    adjudication_window,
    qtbot,
):
    """
    Switching the measurement source must not retain dots from another signal.
    """
    window = adjudication_window
    controller = enable_calipers(window, qtbot)

    qtbot.mouseClick(controller.manual_button, Qt.LeftButton)

    controller.manual_points = [
        (window.adjudication_waveform_start + 4.5, 0.0),
        (window.adjudication_waveform_start + 5.5, 0.0),
    ]
    controller.recalculate()

    assert controller.rate is not None

    current_index = controller.source_dropdown.currentIndex()
    new_index = 1 if current_index == 0 else 0

    controller.source_dropdown.setCurrentIndex(new_index)

    assert controller.manual_points == []
    assert controller.peak_times.size == 0
    assert controller.peak_items == []
    assert controller.rate is None


# =============================================================================
# Projection and navigation
# =============================================================================

def test_projection_uses_full_range_when_panning_far_from_calipers(
    adjudication_window,
    qtbot,
    monkeypatch,
):
    """
    Projection must repeat the selected duration, remain available away from
    its anchor, and avoid rerunning detection during navigation.
    """
    window = adjudication_window
    before = adjudication_snapshot(window)
    controller = enable_calipers(window, qtbot)

    origin = window.adjudication_waveform_start

    controller.start_time = origin + 2.0
    controller.stop_time = origin + 3.0
    controller.redraw()

    qtbot.mouseClick(controller.projection_button, Qt.LeftButton)

    original_marker_times = (
        controller.start_time,
        controller.stop_time,
    )

    def unexpected_detection(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Panning must not rerun peak detection.")

    monkeypatch.setattr(
        controller,
        "_detect_peaks",
        unexpected_detection,
    )
    monkeypatch.setattr(
        controller,
        "recalculate",
        unexpected_detection,
    )

    window.adjudication_waveform_plots[0].setXRange(
        origin + 7.0,
        origin + 9.0,
        padding=0,
    )

    controller.schedule_projection()

    qtbot.waitUntil(
        lambda: any(
            line.value() >= origin + 7.0
            for _plot, line in controller.projection_items
        ),
        timeout=2000,
    )

    # Avoid a pending debounce callback affecting subsequent assertions.
    controller.projection_timer.stop()
    controller.update_projection()

    positions = {
        float(line.value())
        for _plot, line in controller.projection_items
    }

    assert positions

    for position in positions:
        step = (position - controller.start_time) / 1.0

        assert step == pytest.approx(round(step), abs=1e-6)
        assert position != controller.start_time
        assert position != controller.stop_time

    assert (
        controller.start_time,
        controller.stop_time,
    ) == original_marker_times

    assert adjudication_snapshot(window) == before


def test_projection_marker_limit_hides_excessive_graphics(
    adjudication_window,
    qtbot,
    monkeypatch,
):
    """
    Wide views must not create an excessive number of projection line objects.
    """
    import adjudication_calipers as caliper_module

    window = adjudication_window
    controller = enable_calipers(window, qtbot)
    origin = window.adjudication_waveform_start

    controller.start_time = origin + 2.0
    controller.stop_time = origin + 3.0
    controller.redraw()

    monkeypatch.setattr(
        caliper_module,
        "CALIPER_PROJECTION_MAX_MARKERS",
        2,
    )

    window.adjudication_waveform_plots[0].setXRange(
        origin,
        origin + 10.0,
        padding=0,
    )

    qtbot.mouseClick(controller.projection_button, Qt.LeftButton)
    controller.projection_timer.stop()
    controller.update_projection()

    assert controller.projection_requested is True
    assert controller.projection_items == []
    assert "Zoom In" in controller.projection_button.text()


def test_clear_calipers_removes_temporary_graphics(
    adjudication_window,
    qtbot,
):
    """
    Clearing calipers must remove lines, dots, and projections without changing
    permanent adjudication data.
    """
    window = adjudication_window
    before = adjudication_snapshot(window)
    controller = enable_calipers(window, qtbot)

    qtbot.mouseClick(controller.manual_button, Qt.LeftButton)

    controller.manual_points = [
        (window.adjudication_waveform_start + 4.5, 0.0),
        (window.adjudication_waveform_start + 5.5, 0.0),
    ]
    controller.recalculate()

    qtbot.mouseClick(controller.projection_button, Qt.LeftButton)

    assert controller.lines
    assert controller.peak_items
    assert controller.projection_items

    controller.clear()

    assert controller.enabled is False
    assert controller.adjusting is False
    assert controller.manual_labeling is False
    assert controller.lines == []
    assert controller.peak_items == []
    assert controller.projection_items == []
    assert controller.manual_points == []
    assert controller.rate is None
    assert not controller.projection_timer.isActive()
    assert window.adjudication_caliper_adjust_active is False

    assert adjudication_snapshot(window) == before