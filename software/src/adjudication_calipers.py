"""
Temporary waveform calipers for the independent adjudication application.

Features:
- Synchronized draggable start/stop markers.
- Automatic or manual peak measurements.
- Temporary peak dots on the selected source waveform.
- Projection of the complete selected caliper duration.
- Visible-window-only projection rendering.

No caliper data are written to adjudication CSV or JSON files.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from scipy.signal import butter, detrend, find_peaks, sosfiltfilt

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

CALIPER_SIGNAL_SETTINGS: dict[str, dict[str, Any]] = {
    name: {
        "detector": "ecg",
        "unit": "BPM",
        "maximum_rate": 300.0,
    }
    for name in ("I", "II", "III", "V", "AVF", "AVL", "AVR")
}

CALIPER_SIGNAL_SETTINGS["CHEST_IMPEDANCE"] = {
    "detector": "generic",
    "unit": "cycles/min",
    "maximum_rate": 180.0,
}

CALIPER_START_COLOR = "#0066CC"
CALIPER_STOP_COLOR = "#CC3333"
CALIPER_LINE_WIDTH = 3.0
CALIPER_HOVER_WIDTH = 6.0
CALIPER_INITIAL_WINDOW_FRACTION = 0.15
CALIPER_MINIMUM_SEPARATION_SEC = 0.05

CALIPER_AUTO_DOT_COLOR = (180, 0, 180, 230)
CALIPER_MANUAL_DOT_COLOR = (255, 110, 0, 240)
CALIPER_DOT_SIZE = 9

CALIPER_ECG_LOW_HZ = 5.0
CALIPER_ECG_HIGH_HZ = 25.0
CALIPER_ECG_INTEGRATION_SEC = 0.08
CALIPER_ECG_REFINEMENT_SEC = 0.08

# Bound automatic processing to a manageable selected interval.
CALIPER_AUTO_MAX_DURATION_SEC = 120.0
CALIPER_AUTO_MAX_SAMPLES = 100_000

CALIPER_PROJECTION_COLOR = (25, 85, 145, 210)
CALIPER_PROJECTION_WIDTH = 2.0
CALIPER_PROJECTION_MAX_MARKERS = 100
CALIPER_PROJECTION_DEBOUNCE_MS = 40

CALIPER_PERF_ENABLED = True


class AdjudicationCalipers:
    """
    Manage caliper controls, temporary measurements, and graphics.

    Parameters
    ----------
    window : Any
        AdjudicationWindow exposing loaded arrays, plots, and editing controls.

    Notes
    -----
    Source selection determines the measurement signal. Marker adjustment is
    allowed on any displayed waveform.
    """

    def __init__(self, window: Any) -> None:
        self.window = window

        self.enabled = False
        self.adjusting = False
        self.manual_labeling = False
        self.mode = "auto"
        self.auto_enabled = True
        self.projection_requested = False

        self.start_time: Optional[float] = None
        self.stop_time: Optional[float] = None

        # Manual points retain insertion order for Undo.
        self.manual_points: list[tuple[float, float]] = []
        self.peak_times = np.array([], dtype=float)
        self.peak_values = np.array([], dtype=float)
        self.rate: Optional[float] = None
        self.message = ""

        self.lines: list[
            tuple[pg.PlotWidget, str, pg.InfiniteLine]
        ] = []
        self.peak_items: list[tuple[pg.PlotWidget, pg.ScatterPlotItem]] = []
        self.projection_items: list[
            tuple[pg.PlotWidget, pg.InfiniteLine]
        ] = []

        self._synchronizing = False

        self.projection_timer = QTimer(window)
        self.projection_timer.setSingleShot(True)
        self.projection_timer.setInterval(
            CALIPER_PROJECTION_DEBOUNCE_MS
        )
        self.projection_timer.timeout.connect(self.update_projection)

    # =========================================================================
    # Controls and diagnostics
    # =========================================================================

    def build_controls(self) -> QWidget:
        """
        Build all caliper controls in one horizontal row.

        The result label uses remaining space without forcing the window wider.
        """
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(QLabel("Calipers:"))

        self.toggle_button = self._button("OFF", checkable=True)
        self.adjust_button = self._button("Adjust OFF", checkable=True)

        layout.addWidget(self.toggle_button)
        layout.addWidget(self.adjust_button)
        layout.addWidget(QLabel("Source:"))

        self.source_dropdown = QComboBox()
        self.source_dropdown.setMinimumWidth(90)
        self.source_dropdown.setMaximumWidth(140)
        self.source_dropdown.setEnabled(False)
        layout.addWidget(self.source_dropdown)

        self.reset_button = self._button("Reset")
        self.auto_button = self._button("Auto Peaks ON", checkable=True)
        self.auto_button.setChecked(True)

        self.manual_button = self._button(
            "Manual Label OFF",
            checkable=True,
        )
        self.undo_button = self._button("Undo Dot")
        self.clear_dots_button = self._button("Clear Dots")
        self.projection_button = self._button(
            "Projection OFF",
            checkable=True,
        )

        for button in (
            self.reset_button,
            self.auto_button,
            self.manual_button,
            self.undo_button,
            self.clear_dots_button,
            self.projection_button,
        ):
            layout.addWidget(button)

        self.result_label = QLabel("Calipers: Off")
        self.result_label.setMinimumWidth(0)
        self.result_label.setWordWrap(True)
        self.result_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        layout.addWidget(self.result_label, stretch=1)

        self.toggle_button.setToolTip(
            "Turning calipers on resets the markers into the current view."
        )
        self.adjust_button.setToolTip(
            "Drag caliper markers while Adjust is on. "
            "Final adjudication boundary editing is temporarily disabled."
        )
        self.source_dropdown.setToolTip(
            "Select the waveform used for automatic or manual peak measurement."
        )
        self.reset_button.setToolTip(
            "Recenter the calipers in the current visible waveform range."
        )
        self.auto_button.setToolTip(
            "Experimental automatic measurement. Always verify peak dots."
        )
        self.manual_button.setToolTip(
            "Click a displayed row showing the selected source waveform "
            "inside the calipers to add manual dots. Turn Manual Label off "
            "to resume adjudication clicks."
        )
        self.undo_button.setToolTip(
            "Remove the most recently added manual dot."
        )
        self.clear_dots_button.setToolTip(
            "Remove all manual dots from the current measurement."
        )
        self.projection_button.setToolTip(
            "Repeat the complete start-to-stop caliper duration—not the "
            "detected beat interval."
        )

        self.toggle_button.toggled.connect(self.toggle)
        self.adjust_button.toggled.connect(self.set_adjusting)
        self.reset_button.clicked.connect(self.reset)
        self.source_dropdown.currentIndexChanged.connect(
            self.source_changed
        )
        self.auto_button.toggled.connect(self.toggle_auto)
        self.manual_button.toggled.connect(self.toggle_manual)
        self.undo_button.clicked.connect(self.undo_dot)
        self.clear_dots_button.clicked.connect(self.clear_manual_dots)
        self.projection_button.toggled.connect(self.toggle_projection)

        return widget

    @staticmethod
    def _button(
        text: str,
        *,
        checkable: bool = False,
    ) -> QPushButton:
        """Create a control that starts disabled until data are available."""
        button = QPushButton(text)
        button.setCheckable(checkable)
        button.setEnabled(False)
        return button

    def _log(self, operation: str, started: float) -> None:
        """Print elapsed time without logging identifiers or waveform values."""
        if CALIPER_PERF_ENABLED:
            print(
                f"[PERF][ADJ-CAL] {operation}: "
                f"{perf_counter() - started:.4f} sec"
            )

    def _set_checked(self, button: QPushButton, checked: bool) -> None:
        """Change a toggle without recursively emitting its signal."""
        previous = button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(previous)

    def _update_controls(self) -> None:
        """Synchronize controls with temporary caliper state."""
        self._set_checked(self.toggle_button, self.enabled)
        self._set_checked(self.adjust_button, self.adjusting)
        self._set_checked(self.auto_button, self.auto_enabled)
        self._set_checked(self.manual_button, self.manual_labeling)
        self._set_checked(
            self.projection_button,
            self.projection_requested,
        )

        self.toggle_button.setText("ON" if self.enabled else "OFF")
        self.adjust_button.setText(
            "Adjust ON" if self.adjusting else "Adjust OFF"
        )
        self.auto_button.setText(
            "Auto Peaks ON" if self.auto_enabled else "Auto Peaks OFF"
        )
        self.manual_button.setText(
            "Manual Label ON" if self.manual_labeling else "Manual Label OFF"
        )
        self.projection_button.setText(
            "Projection ON" if self.projection_requested else "Projection OFF"
        )

        for button in (
            self.adjust_button,
            self.reset_button,
            self.auto_button,
            self.manual_button,
        ):
            button.setEnabled(self.enabled)

        has_manual_points = (
            self.enabled
            and self.mode == "manual"
            and bool(self.manual_points)
        )
        self.undo_button.setEnabled(has_manual_points)
        self.clear_dots_button.setEnabled(has_manual_points)
        self.projection_button.setEnabled(
            self.enabled and self._duration() is not None
        )

    # =========================================================================
    # Loaded source and range helpers
    # =========================================================================

    def refresh_sources(self) -> None:
        """Populate measurement sources once after loading a waveform."""
        started = perf_counter()

        try:
            self._refresh_sources_impl()
        finally:
            self._log("refresh_sources", started)

    def _refresh_sources_impl(self) -> None:
        """Clear old measurement state and list usable configured signals."""
        self.clear()
        dropdown = self.source_dropdown
        blocked = dropdown.blockSignals(True)

        try:
            dropdown.clear()

            for index, name in enumerate(
                getattr(self.window, "adjudication_lead_names", [])
            ):
                if str(name).upper() not in CALIPER_SIGNAL_SETTINGS:
                    continue

                times, values = self.window._adjudication_signal_arrays(index)

                if np.count_nonzero(
                    np.isfinite(times) & np.isfinite(values)
                ) >= 2:
                    dropdown.addItem(str(name), index)

            preferred = dropdown.findText("II")

            if preferred >= 0:
                dropdown.setCurrentIndex(preferred)
        finally:
            dropdown.blockSignals(blocked)

        available = dropdown.count() > 0
        dropdown.setEnabled(available)
        self.toggle_button.setEnabled(available)

    def _duration(self) -> Optional[float]:
        """Return the complete selected duration, or None for invalid markers."""
        if self.start_time is None or self.stop_time is None:
            return None

        duration = abs(self.stop_time - self.start_time)

        if (
            not np.isfinite(duration)
            or duration < CALIPER_MINIMUM_SEPARATION_SEC
        ):
            return None

        return float(duration)

    def _settings(self) -> dict[str, Any]:
        """Return detector settings for the selected source."""
        return CALIPER_SIGNAL_SETTINGS.get(
            self.source_dropdown.currentText().upper(),
            {
                "detector": "generic",
                "unit": "cycles/min",
                "maximum_rate": 180.0,
            },
        )

    def _selected_samples(self) -> tuple[np.ndarray, np.ndarray]:
        """Extract finite source samples within the absolute caliper range."""
        empty = np.array([], dtype=float)
        index = self.source_dropdown.currentData()

        if index is None or self._duration() is None:
            return empty, empty

        times, values = self.window._adjudication_signal_arrays(int(index))
        left = min(self.start_time, self.stop_time)
        right = max(self.start_time, self.stop_time)

        valid = (
            np.isfinite(times)
            & np.isfinite(values)
            & (times >= left)
            & (times <= right)
        )

        times = times[valid]
        values = values[valid]

        if times.size:
            order = np.argsort(times)
            times, values = times[order], values[order]

            unique = np.r_[True, np.diff(times) > 0]
            times, values = times[unique], values[unique]

        return times, values

    # =========================================================================
    # Enable, reset, and editing modes
    # =========================================================================

    def toggle(self, enabled: bool) -> None:
        """Timed wrapper for enabling or clearing temporary calipers."""
        started = perf_counter()

        try:
            self._toggle_impl(bool(enabled))
        except Exception as exc:
            self.clear()
            self.window.show_adjudication_error("Calipers Failed", str(exc))
        finally:
            self._log("toggle", started)

    def _toggle_impl(self, enabled: bool) -> None:
        """Enable centered markers or remove the current measurement."""
        if not enabled:
            self.clear()
            return

        if self.source_dropdown.count() == 0:
            raise ValueError("No eligible measurement waveform is loaded.")

        self.enabled = True
        self.mode = "auto"
        self.auto_enabled = True
        self._update_controls()
        self.reset()

    def _can_enter_click_mode(self) -> bool:
        """Reject conflicts with pending final-boundary insertion."""
        if self.window.adjudication_pending_split_index is not None:
            self.window.show_adjudication_error(
                "Finish Boundary Placement",
                "Finish or cancel Add Boundary before using this caliper mode.",
            )
            return False

        return True

    def _update_editing_guard(self) -> None:
        """Suspend final-boundary editing during caliper interaction modes."""
        active = self.adjusting or self.manual_labeling

        self.window.adjudication_caliper_adjust_active = active

        for _plot, _role, line in self.lines:
            line.setMovable(self.adjusting)

        if active:
            for line in self.window.adjudication_boundary_lines:
                line.setMovable(False)

            self.window.adjudication_add_boundary_btn.setEnabled(False)
            self.window.adjudication_remove_boundary_btn.setEnabled(False)
        else:
            self.window.draw_adjudication_boundary_handles()
            self.window.update_adjudication_boundary_controls()

    def set_adjusting(self, enabled: bool) -> None:
        """Enable marker dragging without changing final adjudication data."""
        started = perf_counter()

        try:
            enabled = bool(enabled) and self.enabled

            if enabled and not self._can_enter_click_mode():
                self._update_controls()
                return

            self.adjusting = enabled

            if enabled:
                self.manual_labeling = False

            self._update_editing_guard()
            self._update_controls()
        finally:
            self._log("set_adjusting", started)

    def toggle_manual(self, enabled: bool) -> None:
        """Enable manual dot placement or resume ordinary adjudication clicks."""
        started = perf_counter()

        try:
            enabled = bool(enabled) and self.enabled

            if enabled and not self._can_enter_click_mode():
                self._update_controls()
                return

            if enabled:
                if self.mode != "manual":
                    self.manual_points = []
                    self._clear_measurement()

                self.mode = "manual"
                self.auto_enabled = False
                self.adjusting = False

            self.manual_labeling = enabled
            self._update_editing_guard()
            self._update_controls()

            if self.mode == "manual":
                self.recalculate()
        finally:
            self._log("toggle_manual", started)

    def toggle_auto(self, enabled: bool) -> None:
        """Enable automatic detection or clear its temporary measurement."""
        started = perf_counter()

        try:
            self.auto_enabled = bool(enabled) and self.enabled

            if self.auto_enabled:
                self.mode = "auto"
                self.manual_labeling = False
                self.manual_points = []
                self._update_editing_guard()

            self._update_controls()
            self.recalculate()
        finally:
            self._log("toggle_auto", started)

    def reset(self) -> None:
        """Timed wrapper for recentering markers in the visible waveform range."""
        started = perf_counter()

        try:
            self._reset_impl()
        except Exception as exc:
            self.window.show_adjudication_error("Caliper Reset Failed", str(exc))
        finally:
            self._log("reset", started)

    def _reset_impl(self) -> None:
        """Recenter markers, clear old manual points, and update measurement."""
        if not self.enabled:
            return

        x_min, x_max = (
            self.window.adjudication_waveform_plots[0].viewRange()[0]
        )

        left = max(float(x_min), self.window.adjudication_waveform_start)
        right = min(float(x_max), self.window.adjudication_waveform_end)

        if right <= left:
            raise ValueError("Navigate to a range containing waveform data.")

        center = left + (right - left) / 2.0
        separation = (right - left) * CALIPER_INITIAL_WINDOW_FRACTION

        self.start_time = center - separation / 2.0
        self.stop_time = center + separation / 2.0
        self.manual_points = []

        self._clear_measurement()
        self.redraw()
        self.recalculate()
        self._update_controls()

    def source_changed(self, index: int) -> None:
        """Clear stale points and calculate using the newly selected source."""
        if not self.enabled:
            return

        self.manual_points = []
        self._clear_measurement()
        self.recalculate()

    # =========================================================================
    # Marker graphics
    # =========================================================================

    def redraw(self) -> None:
        """
        Restore caliper graphics after lead switching.

        Marker times and calculated values are retained. No peak detection
        runs merely because the displayed lead changed.
        """
        self._remove_items(self.lines)
        self.lines = []

        if not self.enabled or self.start_time is None or self.stop_time is None:
            return

        for plot in self.window.adjudication_waveform_plots:
            for role, position, color in (
                ("start", self.start_time, CALIPER_START_COLOR),
                ("stop", self.stop_time, CALIPER_STOP_COLOR),
            ):
                line = pg.InfiniteLine(
                    pos=position,
                    angle=90,
                    movable=self.adjusting,
                    bounds=[
                        self.window.adjudication_waveform_start,
                        self.window.adjudication_waveform_end,
                    ],
                    pen=pg.mkPen(color, width=CALIPER_LINE_WIDTH),
                    hoverPen=pg.mkPen(color, width=CALIPER_HOVER_WIDTH),
                )
                line.setZValue(10000)

                line.sigPositionChanged.connect(
                    lambda moved, marker_role=role:
                        self._line_moved(marker_role, moved)
                )
                line.sigPositionChangeFinished.connect(
                    self._drag_finished
                )

                plot.addItem(line, ignoreBounds=True)
                self.lines.append((plot, role, line))

        self._draw_peak_dots()
        self.update_projection()

    def _line_moved(self, role: str, moved_line: pg.InfiniteLine) -> None:
        """Synchronize marker positions and invalidate old detected/manual dots."""
        if self._synchronizing:
            return

        position = float(moved_line.value())

        if not np.isfinite(position):
            return

        if role == "start":
            self.start_time = position
        else:
            self.stop_time = position

        self.manual_points = []
        self._clear_measurement()

        self._synchronizing = True

        try:
            for _plot, line_role, line in self.lines:
                if line_role == role and line is not moved_line:
                    line.setValue(position)
        finally:
            self._synchronizing = False

        self.message = "Release marker to calculate."
        self._update_controls()
        self._update_display()
        self.schedule_projection()

    def _drag_finished(self, line: pg.InfiniteLine) -> None:
        """Calculate once after dragging finishes, not for every mouse pixel."""
        self.recalculate()

    @staticmethod
    def _remove_items(items: list[Any]) -> None:
        """Remove graphics owned by this controller."""
        for entry in items:
            plot = entry[0]
            item = entry[-1]

            if item.scene() is not None:
                plot.removeItem(item)

    def _clear_measurement(self) -> None:
        """Clear peaks and rate without changing calipers or projection."""
        self._remove_items(self.peak_items)
        self.peak_items = []
        self.peak_times = np.array([], dtype=float)
        self.peak_values = np.array([], dtype=float)
        self.rate = None
        self.message = ""

    # =========================================================================
    # Automatic detection and measurement
    # =========================================================================

    def recalculate(self) -> None:
        """Calculate a temporary automatic/manual rate with timing."""
        started = perf_counter()

        try:
            self._recalculate_impl()
        except Exception as exc:
            self._clear_measurement()
            self.message = "Unable to calculate—check signal."
            print("[ADJ-CAL] Calculation failed:", type(exc).__name__, exc)
        finally:
            self._draw_peak_dots()
            self._update_display()
            self._update_controls()
            self.update_projection()
            self._log("recalculate", started)

    def _recalculate_impl(self) -> None:
        """Detect peaks or use manual points, then calculate span-based rate."""
        self._clear_measurement()

        if not self.enabled:
            return

        if self.mode == "manual":
            points = sorted(self.manual_points, key=lambda point: point[0])

            self.peak_times = np.asarray(
                [point[0] for point in points],
                dtype=float,
            )
            self.peak_values = np.asarray(
                [point[1] for point in points],
                dtype=float,
            )
            self.message = "Manual"

        elif not self.auto_enabled:
            self.message = "Auto detection off"
            return

        else:
            if not SCIPY_AVAILABLE:
                self.message = "SciPy unavailable"
                return

            duration = self._duration()

            if duration is None:
                self.message = "Adjust calipers"
                return

            if duration > CALIPER_AUTO_MAX_DURATION_SEC:
                self.message = "Select a shorter range for Auto Peaks"
                return

            times, values = self._selected_samples()

            if times.size < 5:
                self.message = "Insufficient waveform samples"
                return

            if times.size > CALIPER_AUTO_MAX_SAMPLES:
                self.message = "Too many samples—select a shorter range"
                return

            differences = np.diff(times)
            median_dt = float(np.median(differences))

            if median_dt <= 0:
                self.message = "Invalid sampling interval"
                return

            # Do not filter disconnected data as if it were continuous.
            if np.any(differences > 3.0 * median_dt):
                self.message = "Data gaps—use Manual Label"
                return

            indices = self._detect_peaks(values, 1.0 / median_dt)
            self.peak_times = times[indices]
            self.peak_values = values[indices]
            self.message = "Auto—verify dots"

        if self.peak_times.size < 2:
            self.message = (
                "Manual: add at least two dots"
                if self.mode == "manual"
                else "Unable: fewer than two peaks"
            )
            return

        span = float(self.peak_times[-1] - self.peak_times[0])

        if span > 0:
            self.rate = 60.0 * (self.peak_times.size - 1) / span

    def _detect_peaks(self, values: np.ndarray, fs: float) -> np.ndarray:
        """
        Detect ECG energy peaks or generic periodic extrema.

        This lightweight detector is not clinically validated. Periodic
        artifact may produce plausible but incorrect detections.
        """
        settings = self._settings()
        minimum_distance = max(
            1,
            int(round(fs * 60.0 / settings["maximum_rate"])),
        )

        signal = detrend(values, type="linear")

        if settings["detector"] == "generic":
            prominence = float(np.std(signal)) * 0.25

            if prominence <= 0:
                return np.array([], dtype=int)

            candidates = []

            for direction in (1.0, -1.0):
                indices, properties = find_peaks(
                    direction * signal,
                    prominence=prominence,
                    distance=minimum_distance,
                )
                strengths = properties.get("prominences", np.array([]))
                score = (
                    float(np.median(strengths)) * indices.size
                    if strengths.size
                    else 0.0
                )
                candidates.append((score, indices))

            return max(candidates, key=lambda item: item[0])[1]

        high_hz = min(CALIPER_ECG_HIGH_HZ, fs * 0.45)

        if high_hz <= CALIPER_ECG_LOW_HZ:
            return np.array([], dtype=int)

        sos = butter(
            2,
            [CALIPER_ECG_LOW_HZ, high_hz],
            btype="bandpass",
            fs=fs,
            output="sos",
        )

        try:
            filtered = sosfiltfilt(sos, signal)
        except ValueError:
            # Too short for zero-phase filtering: return no inferred peaks.
            return np.array([], dtype=int)

        energy = np.diff(filtered, prepend=filtered[0]) ** 2
        window = min(
            energy.size,
            max(1, int(round(CALIPER_ECG_INTEGRATION_SEC * fs))),
        )
        integrated = np.convolve(
            energy,
            np.ones(window) / window,
            mode="same",
        )

        spread = float(np.std(integrated))

        if spread <= 0:
            return np.array([], dtype=int)

        candidates, _ = find_peaks(
            integrated,
            height=float(np.median(integrated)) + 0.35 * spread,
            prominence=0.15 * spread,
            distance=minimum_distance,
        )

        radius = max(1, int(round(CALIPER_ECG_REFINEMENT_SEC * fs)))
        refined = []

        for candidate in candidates:
            left = max(0, candidate - radius)
            right = min(filtered.size, candidate + radius + 1)
            refined.append(
                left + int(np.argmax(np.abs(filtered[left:right])))
            )

        accepted: list[int] = []

        for index in sorted(set(refined)):
            if not accepted or index - accepted[-1] >= minimum_distance:
                accepted.append(index)
            elif abs(filtered[index]) > abs(filtered[accepted[-1]]):
                accepted[-1] = index

        return np.asarray(accepted, dtype=int)

    # =========================================================================
    # Manual dot placement
    # =========================================================================

    def handle_waveform_click(self, row_index: int, event: Any) -> bool:
        """
        Consume a manual-label click before adjudication click handling.

        Returns
        -------
        bool
            True when manual labeling consumed the click.
        """
        if not self.enabled or not self.manual_labeling:
            return False

        if event.button() != Qt.LeftButton:
            return False

        started = perf_counter()

        try:
            self._handle_waveform_click_impl(row_index, event)
        finally:
            self._log("manual_dot_click", started)

        return True

    def _handle_waveform_click_impl(
        self,
        row_index: int,
        event: Any,
    ) -> None:
        """Snap a click to the nearest finite selected-source sample."""
        displayed_source = (
            self.window.adjudication_lead_selectors[row_index].currentData()
        )

        if displayed_source != self.source_dropdown.currentData():
            self.message = "Click a displayed row showing the selected source"
            self._update_display()
            return

        plot = self.window.adjudication_waveform_plots[row_index]
        view = plot.getViewBox()

        if not view.sceneBoundingRect().contains(event.scenePos()):
            return

        clicked_time = float(view.mapSceneToView(event.scenePos()).x())
        times, values = self._selected_samples()

        if not times.size:
            return

        left = min(self.start_time, self.stop_time)
        right = max(self.start_time, self.stop_time)

        if not left <= clicked_time <= right:
            self.message = "Click inside the calipers"
            self._update_display()
            return

        insertion = int(np.searchsorted(times, clicked_time))
        candidates = {
            max(0, min(insertion, times.size - 1)),
            max(0, min(insertion - 1, times.size - 1)),
        }
        nearest = min(
            candidates,
            key=lambda index: abs(times[index] - clicked_time),
        )

        peak_time = float(times[nearest])

        if any(
            abs(existing_time - peak_time) <= 1e-6
            for existing_time, _value in self.manual_points
        ):
            return

        self.manual_points.append((peak_time, float(values[nearest])))
        self.recalculate()

    def undo_dot(self) -> None:
        """Remove the most recently added manual dot and recalculate."""
        if self.manual_points:
            self.manual_points.pop()
            self.recalculate()

    def clear_manual_dots(self) -> None:
        """Clear manual dots while retaining the current caliper selection."""
        self.manual_points = []
        self.recalculate()

    def _draw_peak_dots(self) -> None:
        """Draw temporary dots only on rows displaying the selected source."""
        self._remove_items(self.peak_items)
        self.peak_items = []

        if not self.enabled or not self.peak_times.size:
            return

        source = self.source_dropdown.currentData()
        color = (
            CALIPER_MANUAL_DOT_COLOR
            if self.mode == "manual"
            else CALIPER_AUTO_DOT_COLOR
        )

        for row, selector in enumerate(
            self.window.adjudication_lead_selectors
        ):
            if selector.currentData() != source:
                continue

            plot = self.window.adjudication_waveform_plots[row]
            dots = pg.ScatterPlotItem(
                x=self.peak_times,
                y=self.peak_values,
                symbol="o",
                size=CALIPER_DOT_SIZE,
                pen=pg.mkPen("w", width=1),
                brush=pg.mkBrush(*color),
            )
            dots.setZValue(11000)
            plot.addItem(dots, ignoreBounds=True)
            self.peak_items.append((plot, dots))

    # =========================================================================
    # Full-selected-range projection
    # =========================================================================

    def toggle_projection(self, enabled: bool) -> None:
        """Toggle projection independently of automatic/manual measurement."""
        self.projection_requested = bool(enabled) and self.enabled
        self._update_controls()
        self.update_projection()

    def schedule_projection(self, *args: Any) -> None:
        """Debounce projection rendering after marker or X-range changes."""
        if self.enabled and self.projection_requested:
            self.projection_timer.start()

    def update_projection(self) -> None:
        """Render only visible full-range projection lines with timing."""
        started = perf_counter()

        try:
            self._update_projection_impl()
        finally:
            self._log("update_projection", started)

    def _update_projection_impl(self) -> None:
        """Generate projections before start and after stop, excluding both."""
        self._remove_items(self.projection_items)
        self.projection_items = []

        duration = self._duration()

        if not self.enabled or not self.projection_requested or duration is None:
            return

        start = min(self.start_time, self.stop_time)
        stop = max(self.start_time, self.stop_time)
        x_min, x_max = (
            self.window.adjudication_waveform_plots[0].viewRange()[0]
        )

        # Bound calculations to the current view, not distance from the anchor.
        lower = max(
            float(x_min) - duration,
            self.window.adjudication_waveform_start,
        )
        upper = min(
            float(x_max) + duration,
            self.window.adjudication_waveform_end,
        )

        if upper < lower:
            return

        first = int(np.ceil((lower - start) / duration))
        last = int(np.floor((upper - start) / duration))

        # k=0 is the start caliper; k=1 is the stop caliper.
        # Neither needs an additional projected line.
        excluded = int(first <= 0 <= last) + int(first <= 1 <= last)
        count = max(0, last - first + 1 - excluded)

        if count > CALIPER_PROJECTION_MAX_MARKERS:
            self.projection_button.setText("Projection: Zoom In")
            return

        self.projection_button.setText("Projection ON")
        pen = pg.mkPen(
            CALIPER_PROJECTION_COLOR,
            width=CALIPER_PROJECTION_WIDTH,
            style=Qt.DotLine,
        )

        for step in range(first, last + 1):
            if step in (0, 1):
                continue

            position = start + step * duration

            for plot in self.window.adjudication_waveform_plots:
                line = pg.InfiniteLine(
                    pos=position,
                    angle=90,
                    movable=False,
                    pen=pen,
                )
                line.setZValue(100)
                plot.addItem(line, ignoreBounds=True)
                self.projection_items.append((plot, line))

    # =========================================================================
    # Display and cleanup
    # =========================================================================

    def _update_display(self) -> None:
        """Display the temporary result and its measurement limitations."""
        if not self.enabled:
            self.result_label.setText("Calipers: Off")
            return

        source = self.source_dropdown.currentText()
        duration = self._duration()
        duration_text = (
            f"{duration:.3f} s"
            if duration is not None
            else "Invalid range"
        )

        if self.rate is None:
            text = f"{source} | {duration_text} | {self.message}"
        else:
            unit = self._settings()["unit"]
            text = (
                f"{source} | {self.peak_times.size} peaks | "
                f"{self.rate:.1f} {unit} | {self.message}"
            )

        self.result_label.setText(text)
        self.result_label.setToolTip(
            f"Selected duration: {duration_text}\n"
            "Rate = 60 × intervals / time between first and last peak.\n"
            "Projection repeats the complete selected caliper duration.\n"
            "Automatic detections require visual verification, especially "
            "during CPR, pacing, noise, and abnormal rhythms.\n"
            "Measurements are temporary and are not saved."
        )

    def clear(self) -> None:
        """Remove all temporary measurement state without changing final data."""
        was_active = self.adjusting or self.manual_labeling

        self.projection_timer.stop()
        self._remove_items(self.lines)
        self.lines = []
        self._remove_items(self.projection_items)
        self.projection_items = []
        self._clear_measurement()

        self.enabled = False
        self.adjusting = False
        self.manual_labeling = False
        self.auto_enabled = True
        self.mode = "auto"
        self.projection_requested = False
        self.manual_points = []
        self.start_time = None
        self.stop_time = None

        self.window.adjudication_caliper_adjust_active = False

        if hasattr(self, "toggle_button"):
            self._update_controls()
            self._update_display()

        if was_active:
            self.window.draw_adjudication_boundary_handles()
            self.window.update_adjudication_boundary_controls()