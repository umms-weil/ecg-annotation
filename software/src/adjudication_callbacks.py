"""
Callbacks for the independent adjudication application.

This implementation supports:
- Batch-folder discovery.
- Waveform-record selection.
- Waveform loading and lead selection.
- Basic Y-axis controls.
- Read-only annotator, comparison, and final timelines.

It does not write files or modify source annotations.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Optional

import numpy as np
import pyqtgraph as pg
from copy import deepcopy

from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PyQt5.QtCore import Qt

from processing import list_subjects, load_waveforms_for_subject
from adjudication import build_adjudication_comparison
from adjudication.config import ComparisonStatus
from adjudication.models import AdjudicationComparisonResult, AdjudicationInterval
from adjudication.persistence import (
    load_existing_adjudication,
    save_adjudication_draft,
    save_reopened_adjudication_draft,
    save_completed_adjudication,
    validate_adjudication_for_finalization,
)

from dataclasses import replace
from adjudication.config import (
    MINIMUM_VALID_INTERVAL_SEC,
    VALID_TERMINAL_EVENT_STATUSES,
)
from adjudication.utilities import utc_now_iso

UM_MAIZE: str = "#FFCB05"
UM_BLUE: str = "#00274C"
UM_ACCENT: str = "#285680"
UM_RED: str = "#B71234"

ADJUDICATION_UI_PERF_ENABLED: bool = True

ADJUDICATION_WAVEFORM_ORDER: list[str] = [
    "I",
    "II",
    "III",
    "V",
    "AVF",
    "AVL",
    "CHEST_IMPEDANCE",
]

# =============================================================================
# Waveform overlay configuration
# =============================================================================

ADJUDICATION_OVERLAY_COLORS: dict[str, tuple[int, int, int]] = {
    "Normal Heart Rhythm": (0, 158, 96),
    "Sinus tachycardia": (255, 128, 0),
    "Bradycardia": (0, 0, 200),
    "Supraventricular tachycardia": (180, 80, 160),
    "Atrial Flutter": (255, 0, 128),
    "Atrial Fibrillation": (200, 0, 0),
    "Ventricular Tachycardia": (204, 102, 0),
    "Ventricular Fibrillation": (153, 102, 51),
    "Unable to Determine": (130, 130, 130),
    "Other": (204, 204, 0),
}

ADJUDICATION_OVERLAY_DEFAULT_COLOR: tuple[int, int, int] = (
    130,
    130,
    130,
)

ADJUDICATION_OVERLAY_ALPHA: dict[str, int] = {
    "Annotator A": 50,
    "Annotator B": 50,
    "Final": 45,
}

ADJUDICATION_OVERLAY_LINE_WIDTHS: dict[str, float] = {
    "Annotator A": 3.0,
    "Annotator B": 3.0,
    "Final": 2.0,
}

ADJUDICATION_OVERLAY_LINE_COLORS: dict[str, str] = {
    "Annotator A": "#00274C",
    "Annotator B": "#B71234",
    "Final": "#199E40",
}

# Fractions of the plot height: (bottom, top).
ADJUDICATION_OVERLAY_SPANS: dict[str, tuple[float, float]] = {
    "Annotator A": (0.5, 1.0),
    "Annotator B": (0.0, 0.5),
    "Final": (0.0, 1.0),
}

class AdjudicationRelativeAxis(pg.AxisItem):
    """Display relative seconds while retaining absolute epoch coordinates."""

    def __init__(
        self,
        origin: float,
        orientation: str = "bottom",
    ) -> None:
        super().__init__(orientation=orientation)
        self.origin = origin

    def tickStrings(
        self,
        values: list[float],
        scale: float,
        spacing: float,
    ) -> list[str]:
        """Format axis ticks relative to the loaded waveform start."""
        return [
            f"{value - self.origin:.1f}"
            for value in values
        ]


class AdjudicationAppCallbacks:
    """Connect the independent reviewer UI to waveform and comparison logic."""

    def _adjudication_perf_log(
        self,
        operation: str,
        elapsed_seconds: float,
    ) -> None:
        """Print an adjudication UI timing measurement."""
        if ADJUDICATION_UI_PERF_ENABLED:
            print(
                f"[PERF][ADJ-UI] {operation}: "
                f"{elapsed_seconds:.4f} sec"
            )

    # =========================================================================
    # Folder discovery
    # =========================================================================

    def browse_adjudication_base_folder(self) -> None:
        """Select a batch folder and discover its waveform records."""
        started = perf_counter()

        try:
            self._browse_adjudication_base_folder_impl()
        except Exception as exc:
            print("[ADJ-UI] Discovery failed:", repr(exc))
            self.show_adjudication_error(
                "Record Discovery Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "browse_adjudication_base_folder",
                perf_counter() - started,
            )

    def _browse_adjudication_base_folder_impl(self) -> None:
        """Select a batch folder and pass it to the shared folder-loading method."""
        current = self.adjudication_folder_input.text().strip()
        initial = Path(current).expanduser() if current else Path.home()

        if not initial.is_dir():
            initial = Path.home()

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Annotation Batch Folder",
            str(initial),
        )

        if not folder:
            return

        self.adjudication_folder_input.setText(folder)
        self._set_adjudication_base_folder_impl()


    def update_adjudication_load_availability(
        self,
        *args: Any,
    ) -> None:
        """
        Enable loading/resuming when a reviewer and record are selected.

        No network existence checks are performed during dropdown selection.
        """
        has_reviewer = bool(self.adjudicator_dropdown.currentData())
        has_record = isinstance(
            self.adjudication_subject_dropdown.currentData(),
            dict,
        )

        available = has_reviewer and has_record

        self.adjudication_load_btn.setEnabled(available)
        self.adjudication_resume_btn.setEnabled(available)    

    def set_adjudication_base_folder(self) -> None:
        """
        Load waveform records from the pasted batch-folder path.

        Supports the Set Folder button and Enter in the folder input.
        """
        started = perf_counter()

        try:
            self._set_adjudication_base_folder_impl()
        except Exception as exc:
            print("[ADJ-UI] Folder discovery failed:", repr(exc))
            self.adjudication_status_label.setText(
                f"Folder discovery failed: {exc}"
            )
            self.show_adjudication_error(
                "Record Discovery Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "set_adjudication_base_folder",
                perf_counter() - started,
            )


    def _set_adjudication_base_folder_impl(self) -> None:
        """Validate the input path and discover records for the selected batch."""
        if not self.confirm_discard_adjudication_changes():
            return
        raw_path = (
            self.adjudication_folder_input.text()
            .strip()
            .strip('"')
            .strip("'")
        )

        if not raw_path:
            raise ValueError("Enter an annotation batch folder path.")

        folder = Path(raw_path).expanduser()

        if not folder.is_dir():
            raise ValueError(
                f"Folder does not exist or is inaccessible: {folder}"
            )

        # Discovery must finish before replacing the displayed session.
        self.adjudication_status_label.setText(
            "Discovering waveform records…"
        )

        discovery_started = perf_counter()
        records = list_subjects(str(folder), user_name="")

        self._adjudication_perf_log(
            "discover_waveform_records",
            perf_counter() - discovery_started,
        )

        self._clear_adjudication_display()

        self.adjudication_base_folder = str(folder)
        self.adjudication_folder_input.setText(str(folder))
        self.adjudication_records = [
            dict(record)
            for record in records
        ]

        dropdown = self.adjudication_subject_dropdown
        previous_blocked = dropdown.blockSignals(True)

        try:
            dropdown.clear()

            for record in self.adjudication_records:
                dropdown.addItem(
                    str(record.get("name", "Waveform record")),
                    record,
                )

            dropdown.setEnabled(bool(self.adjudication_records))
        finally:
            dropdown.blockSignals(previous_blocked)

        self.adjudication_status_label.setText(
            f"Found {len(self.adjudication_records)} waveform records. "
            "Select an adjudicator and record, then load."
        )

        self.update_adjudication_load_availability()


    # =========================================================================
    # Waveform annotation overlays
    # =========================================================================

    def clear_adjudication_waveform_overlays(
        self,
        plot: Optional[pg.PlotWidget] = None,
    ) -> None:
        """
        Remove temporary annotation overlays from one or all waveform plots.

        Waveform curves, selection highlights, and timeline graphics are retained.
        """
        retained: list[
            tuple[pg.PlotWidget, pg.LinearRegionItem]
        ] = []

        for owner_plot, item in self.adjudication_waveform_overlay_graphics:
            if plot is not None and owner_plot is not plot:
                retained.append((owner_plot, item))
                continue

            # A lead change may already have removed the item through plot.clear().
            if item.scene() is not None:
                owner_plot.removeItem(item)

        self.adjudication_waveform_overlay_graphics = retained


    def draw_adjudication_waveform_overlays(
        self,
        row_index: Optional[int] = None,
    ) -> None:
        """
        Draw enabled source and final overlays with performance diagnostics.

        Parameters
        ----------
        row_index : int or None
            Draw one waveform row, or every displayed row when omitted.
        """
        started = perf_counter()

        try:
            self._draw_adjudication_waveform_overlays_impl(row_index)
        except Exception as exc:
            print("[ADJ-UI] Waveform overlay drawing failed:", repr(exc))
            raise
        finally:
            self._adjudication_perf_log(
                "draw_adjudication_waveform_overlays",
                perf_counter() - started,
            )


    def _draw_adjudication_waveform_overlays_impl(
        self,
        row_index: Optional[int],
    ) -> None:
        """
        Render vertically separated annotator overlays.

        Annotator A occupies the upper half of the plot.
        Annotator B occupies the lower half.
        Final adjudication occupies the entire height when enabled.

        Region spans use plot-height fractions rather than signal amplitude.
        """
        comparison = self.adjudication_comparison

        if row_index is None:
            rows = range(len(self.adjudication_waveform_plots))
            self.clear_adjudication_waveform_overlays()
        else:
            if not 0 <= row_index < len(self.adjudication_waveform_plots):
                raise ValueError("Invalid waveform row for overlay rendering.")

            rows = [row_index]
            self.clear_adjudication_waveform_overlays(
                self.adjudication_waveform_plots[row_index]
            )

        if comparison is None:
            return

        tracks = {
            "Annotator A": comparison.annotator_a_intervals,
            "Annotator B": comparison.annotator_b_intervals,
            "Final": comparison.prefilled_intervals,
        }

        edge_styles = {
            "Annotator A": Qt.DashLine,
            "Annotator B": Qt.DotLine,
            "Final": Qt.SolidLine,
        }

        for row in rows:
            plot = self.adjudication_waveform_plots[row]

            if self.adjudication_lead_selectors[row].currentData() is None:
                continue

            for track_name, intervals in tracks.items():
                if not self.adjudication_overlay_checks[
                    track_name
                ].isChecked():
                    continue

                for interval in intervals:
                    if interval.cpr == "Yes":
                        label = "CPR: Yes"
                        rgb = (80, 80, 80)

                    elif interval.cpr == "Unable to Determine":
                        label = "CPR: Unable to Determine"
                        rgb = (130, 130, 130)

                    else:
                        label = interval.rhythm_label or "Needs review"
                        rgb = ADJUDICATION_OVERLAY_COLORS.get(
                            interval.rhythm_label,
                            ADJUDICATION_OVERLAY_DEFAULT_COLOR,
                        )

                    overlay = pg.LinearRegionItem(
                        values=[
                            float(interval.start),
                            float(interval.end),
                        ],
                        orientation="vertical",
                        span=ADJUDICATION_OVERLAY_SPANS[track_name],
                        movable=False,
                        brush=pg.mkBrush(
                            *rgb,
                            ADJUDICATION_OVERLAY_ALPHA[track_name],
                        ),
                        pen=pg.mkPen(
                            ADJUDICATION_OVERLAY_LINE_COLORS[track_name],
                            width=ADJUDICATION_OVERLAY_LINE_WIDTHS[track_name],
                            style=edge_styles[track_name],
                        ),
                    )

                    overlay.setZValue(
                        20 if track_name == "Final" else 10
                    )

                    overlay.setToolTip(
                        f"{track_name}\n"
                        f"CPR: {interval.cpr or 'Missing'}\n"
                        f"Label: {label}\n"
                        f"Explanation: {interval.rhythm_expl or 'None'}\n"
                        f"Start: {interval.start:.6f}\n"
                        f"End: {interval.end:.6f}"
                    )

                    plot.addItem(overlay, ignoreBounds=True)

                    self.adjudication_waveform_overlay_graphics.append(
                        (plot, overlay)
                    )

    def handle_adjudication_overlay_toggle(
        self,
        checked: bool,
    ) -> None:
        """
        Refresh waveform overlays after a visibility checkbox changes.

        The checked argument is supplied by Qt. Actual track visibility is read
        from each checkbox.
        """
        self.draw_adjudication_waveform_overlays()


    def update_adjudication_overlay_controls(self) -> None:
        """
        Enable overlay toggles when a comparison is available.

        Read-only completed adjudications may still change overlay visibility.
        """
        available = self.adjudication_comparison is not None

        for checkbox in self.adjudication_overlay_checks.values():
            checkbox.setEnabled(available)

    # =========================================================================
    # Waveform and comparison loading
    # =========================================================================

    def load_adjudication_record(self) -> None:
        """Load the selected waveform and its two-user comparison."""
        started = perf_counter()
        self.adjudication_load_btn.setEnabled(False)

        try:
            self._load_adjudication_record_impl()
        except Exception as exc:
            print("[ADJ-UI] Record load failed:", repr(exc))
            self.adjudication_status_label.setText(
                f"Load failed: {exc}"
            )
            self.show_adjudication_error(
                "Adjudication Load Failed",
                str(exc),
            )
        finally:
            self.update_adjudication_load_availability()
            self._adjudication_perf_log(
                "load_adjudication_record",
                perf_counter() - started,
            )


    def _load_adjudication_record_impl(self) -> None:
        """Load waveform arrays first, then construct the comparison."""

        if not self.confirm_discard_adjudication_changes():
            return
        
        record = self.adjudication_subject_dropdown.currentData()
        reviewer = self.adjudicator_dropdown.currentData()

        if not isinstance(record, dict) or not reviewer:
            raise ValueError("Select a waveform record and adjudicator.")

        self._clear_adjudication_display()
        self.adjudication_loaded_record = dict(record)
        self.adjudication_loaded_reviewer = str(reviewer)

        self.adjudication_status_label.setText("Loading waveform…")

        waveform_started = perf_counter()
        loaded = load_waveforms_for_subject(
            self.adjudication_base_folder,
            record,
            recording_start_sec=None,
            code_start_sec=None,
            code_stop_sec=None,
            desired_waveforms=ADJUDICATION_WAVEFORM_ORDER,
        )

        self._adjudication_perf_log(
            "load_waveforms_for_subject",
            perf_counter() - waveform_started,
        )

        global_times = loaded.get("times_ds")
        self.adjudication_time_axis = np.asarray(
            [] if global_times is None else global_times,
            dtype=np.float64,
        )

        leads = loaded.get("leads_ds")
        names = loaded.get("lead_names")
        units = loaded.get("units")

        self.adjudication_leads = [] if leads is None else leads
        self.adjudication_lead_names = [] if names is None else names
        self.adjudication_units = [] if units is None else units

        per_lead_times = loaded.get("times_by_lead")

        if per_lead_times is None:
            self.adjudication_times_by_lead = [
                self.adjudication_time_axis
                for _ in self.adjudication_leads
            ]
        else:
            self.adjudication_times_by_lead = [
                np.asarray(
                    [] if values is None else values,
                    dtype=np.float64,
                )
                for values in per_lead_times
            ]

        available_indices: list[int] = []
        starts: list[float] = []
        stops: list[float] = []

        for index in range(len(self.adjudication_leads)):
            times, values = self._adjudication_signal_arrays(index)
            finite = np.isfinite(times) & np.isfinite(values)

            if not np.any(finite):
                continue

            available_indices.append(index)
            starts.append(float(np.min(times[finite])))
            stops.append(float(np.max(times[finite])))

        if not available_indices:
            raise ValueError("No finite waveform data were loaded.")

        self.adjudication_waveform_start = min(starts)
        self.adjudication_waveform_end = max(stops)

        self._populate_adjudication_lead_selectors(available_indices)

        all_plots = (
            self.adjudication_waveform_plots
            + list(self.adjudication_timeline_plots.values())
        )

        for plot in all_plots:
            plot.setAxisItems(
                {
                    "bottom": AdjudicationRelativeAxis(
                        self.adjudication_waveform_start
                    )
                }
            )
            plot.hideAxis("bottom")

        final_plot = self.adjudication_timeline_plots["Final Adjudication"]
        final_plot.showAxis("bottom")
        final_plot.setLabel("bottom", "Seconds from loaded waveform start")

        right = min(
            self.adjudication_waveform_end,
            self.adjudication_waveform_start + 10.0,
        )

        self.adjudication_waveform_plots[0].setXRange(
            self.adjudication_waveform_start,
            max(right, self.adjudication_waveform_start + 0.001),
            padding=0,
        )

        self.adjudication_status_label.setText("Loading annotation comparison…")

        # Missing/invalid source files leave waveform viewing available.
        comparison = build_adjudication_comparison(
            record=record,
            adjudicator=str(reviewer),
        )

        self.adjudication_comparison = comparison
        self.draw_adjudication_timelines()

        self.populate_adjudication_table()
        self.update_adjudication_navigation_controls()

        if comparison.prefilled_intervals:
            self.select_adjudication_interval(0)

        self.update_adjudication_navigation_controls()

        self.adjudication_input_status.setText(
            f"Annotator A: {len(comparison.annotator_a_intervals)} intervals\n"
            f"Annotator B: {len(comparison.annotator_b_intervals)} intervals"
        )
        self.adjudication_progress_label.setText(
            f"Unresolved regions: {len(comparison.unresolved_regions)}"
        )
        self.adjudication_status_label.setText(
            "Comparison loaded. Edit final labels, explicitly resolve review "
            "regions, and save a draft. Finalization is not enabled yet."
        )

        self.adjudication_save_btn.setEnabled(True)
        self.adjudication_save_status.setText("Draft has not been saved yet.")

        self.adjudication_finalize_btn.setEnabled(True)


    def _clear_adjudication_display(self) -> None:
        """Remove stale displayed data without modifying any files."""

        self.clear_adjudication_waveform_overlays()

        for checkbox in self.adjudication_overlay_checks.values():
            checkbox.setEnabled(False)

        self.adjudication_reopened_from_complete = False
        self.adjudication_reopen_btn.setEnabled(False)

        self.adjudication_complete = False
        self.adjudication_finalize_btn.setEnabled(False)

        self._clear_adjudication_selection_graphics()

        self.adjudication_pending_split_index = None
        self.adjudication_add_boundary_btn.setText("Add Boundary")

        self.adjudication_save_btn.setEnabled(False)
        self.adjudication_save_status.setText("")

        self.adjudication_selected_interval_index = None
        self.adjudication_selected_region_id = None

        self.adjudication_previous_btn.setEnabled(False)
        self.adjudication_next_btn.setEnabled(False)

        self.adjudication_selection_label.setText(
            "No interval selected.\nStart: —   End: —\nDuration: —"
        )
        self.adjudication_comparison_details.setText(
            "Select a region to inspect the source labels."
        )

        self.adjudication_cpr_dropdown.setCurrentIndex(0)
        self.adjudication_rhythm_dropdown.setCurrentIndex(0)
        self.adjudication_explanation.clear()

        self.adjudication_comparison = None
        self.adjudication_input_status.setText(
            "Annotator A: Not loaded\nAnnotator B: Not loaded"
        )
        self.adjudication_progress_label.setText(
            "Unresolved regions: Not loaded"
        )
        self.adjudication_table.setRowCount(0)

        for plot in (
            self.adjudication_waveform_plots
            + list(self.adjudication_timeline_plots.values())
        ):
            plot.clear()

        for selector in self.adjudication_lead_selectors:
            blocked = selector.blockSignals(True)
            selector.clear()
            selector.setEnabled(False)
            selector.blockSignals(blocked)

        for controls in self.adjudication_y_controls:
            for button in controls.values():
                button.setEnabled(False)

        self.adjudication_dirty = False

        # plot.clear() removed the graphics; discard the old references.
        self.adjudication_boundary_lines = []
        self.adjudication_add_boundary_btn.setEnabled(False)
        self.adjudication_remove_boundary_btn.setEnabled(False)

        self.adjudication_apply_btn.setEnabled(False)
        self.adjudication_resolve_btn.setEnabled(False)
        self.adjudication_cpr_dropdown.setEnabled(False)
        self.adjudication_rhythm_dropdown.setEnabled(False)
        self.adjudication_explanation.setEnabled(False)


    # =========================================================================
    # Lead selection and waveform rendering
    # =========================================================================

    def _adjudication_signal_arrays(
        self,
        signal_index: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return matched time/value arrays for a loaded signal."""
        empty = np.array([], dtype=np.float64)

        leads = getattr(self, "adjudication_leads", [])

        if signal_index < 0 or signal_index >= len(leads):
            return empty, empty

        signal = leads[signal_index]

        if signal is None:
            return empty, empty

        values = np.asarray(signal, dtype=float)

        axes = getattr(self, "adjudication_times_by_lead", [])

        if signal_index < len(axes) and len(axes[signal_index]):
            times = np.asarray(axes[signal_index], dtype=np.float64)
        else:
            times = getattr(self, "adjudication_time_axis", empty)

        count = min(len(times), len(values))
        return times[:count], values[:count]

    def _populate_adjudication_lead_selectors(
        self,
        available_indices: list[int],
    ) -> None:
        """Populate three independent selectors from loaded usable signals."""
        for row_index, selector in enumerate(
            self.adjudication_lead_selectors
        ):
            blocked = selector.blockSignals(True)

            try:
                selector.clear()

                for signal_index in available_indices:
                    name = self.adjudication_lead_names[signal_index]
                    selector.addItem(str(name), signal_index)

                selector.setCurrentIndex(
                    min(row_index, len(available_indices) - 1)
                )
                selector.setEnabled(True)
            finally:
                selector.blockSignals(blocked)

            self.draw_adjudication_waveform(row_index)

    def draw_adjudication_waveform(self, row_index: int) -> None:
        """Draw one selected lead with timing diagnostics."""
        started = perf_counter()

        try:
            self._draw_adjudication_waveform_impl(row_index)
        finally:
            self._adjudication_perf_log(
                f"draw_adjudication_waveform row={row_index}",
                perf_counter() - started,
            )

    def _draw_adjudication_waveform_impl(self, row_index: int) -> None:
        """Render the selected signal without rereading its source file."""
        selector = self.adjudication_lead_selectors[row_index]
        signal_index = selector.currentData()
        plot = self.adjudication_waveform_plots[row_index]
        plot.clear()

        if signal_index is None:
            return

        times, values = self._adjudication_signal_arrays(int(signal_index))
        finite = np.isfinite(times) & np.isfinite(values)

        if not np.any(finite):
            return

        times = times[finite]
        values = values[finite]
        order = np.argsort(times)

        curve = plot.plot(
            times[order],
            values[order],
            pen="b",
        )
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method="peak")

        name = str(self.adjudication_lead_names[int(signal_index)])
        units = self.adjudication_units

        unit = (
            str(units[int(signal_index)] or "")
            if int(signal_index) < len(units)
            else ""
        )

        plot.setLabel("left", name, units=unit or None)
        self.adjust_adjudication_y(row_index, "auto")

        for button in self.adjudication_y_controls[row_index].values():
            button.setEnabled(True)

        # plot.clear() removed this row's overlays; recreate them for the new lead.
        self.draw_adjudication_waveform_overlays(row_index)

    def adjust_adjudication_y(
        self,
        row_index: int,
        action: str,
    ) -> None:
        """Apply a manual Y-axis adjustment or autoscale the visible segment."""
        plot = self.adjudication_waveform_plots[row_index]
        low, high = plot.viewRange()[1]
        center = (low + high) / 2.0
        span = max(high - low, 0.001)

        if action == "auto":
            signal_index = (
                self.adjudication_lead_selectors[row_index].currentData()
            )

            if signal_index is None:
                return

            times, values = self._adjudication_signal_arrays(int(signal_index))
            x_low, x_high = plot.viewRange()[0]

            valid = (
                np.isfinite(times)
                & np.isfinite(values)
                & (times >= x_low)
                & (times <= x_high)
            )

            segment = values[valid]

            if segment.size < 2:
                segment = values[np.isfinite(values)]

            if segment.size < 2:
                return

            low, high = np.percentile(segment, [0.5, 99.5])
            margin = max(float(high - low) * 0.1, 0.05)
            low, high = float(low - margin), float(high + margin)

        else:
            if action == "in":
                span *= 0.8
            elif action == "out":
                span *= 1.25
            elif action == "up":
                center += span * 0.2
            elif action == "down":
                center -= span * 0.2

            low, high = center - span / 2.0, center + span / 2.0

        plot.setYRange(low, high, padding=0)

    # =========================================================================
    # Read-only timelines
    # =========================================================================

    def draw_adjudication_timelines(self) -> None:
        """Draw source, comparison, and final timelines with timing."""
        started = perf_counter()

        try:
            self._draw_adjudication_timelines_impl()
        finally:
            self._adjudication_perf_log(
                "draw_adjudication_timelines",
                perf_counter() - started,
            )

    def _draw_adjudication_timelines_impl(self) -> None:
        """Render absolute-time intervals as read-only timeline regions."""
        comparison: Optional[AdjudicationComparisonResult] = (
            self.adjudication_comparison
        )

        if comparison is None:
            return

        for plot in self.adjudication_timeline_plots.values():
            plot.clear()

        for track_name, intervals in (
            ("Annotator A", comparison.annotator_a_intervals),
            ("Annotator B", comparison.annotator_b_intervals),
            ("Final Adjudication", comparison.prefilled_intervals),
        ):
            plot = self.adjudication_timeline_plots[track_name]

            for interval in intervals:
                label = (
                    f"CPR: {interval.cpr}"
                    if interval.cpr in {"Yes", "Unable to Determine"}
                    else interval.rhythm_label or "Needs review"
                )

                self._add_adjudication_timeline_region(
                    plot,
                    interval.start,
                    interval.end,
                    label,
                    (40, 86, 128, 100),
                )

        status_colors = {
            ComparisonStatus.AGREEMENT: (25, 158, 64, 150),
            ComparisonStatus.UNRESOLVED_DISAGREEMENT: (213, 0, 50, 150),
            ComparisonStatus.MISSING_COVERAGE: (136, 136, 136, 150),
            ComparisonStatus.RESOLVED_DISAGREEMENT: (40, 120, 181, 150),
        }

        summary_plot = self.adjudication_timeline_plots["Agreement / Review"]

        for region in comparison.comparison_regions:
            self._add_adjudication_timeline_region(
                summary_plot,
                region.start,
                region.end,
                region.status.value.replace("_", " "),
                status_colors[region.status],
            )

        # Handles are created last and only on the editable final timeline.
        self.draw_adjudication_boundary_handles()

        # Final-label and structural edits already redraw timelines through this path.
        self.update_adjudication_overlay_controls()
        self.draw_adjudication_waveform_overlays()

    def _add_adjudication_timeline_region(
        self,
        plot: pg.PlotWidget,
        start: float,
        end: float,
        label: str,
        color: tuple[int, int, int, int],
    ) -> None:
        """Add one read-only region and its text without affecting plot bounds."""
        region = pg.LinearRegionItem(
            values=[float(start), float(end)],
            movable=False,
            brush=pg.mkBrush(*color),
        )
        plot.addItem(region, ignoreBounds=True)

        text = pg.TextItem(
            str(label),
            color="#00274C",
            anchor=(0.5, 0.5),
        )
        text.setPos((float(start) + float(end)) / 2.0, 0.5)
        plot.addItem(text, ignoreBounds=True)

    # =========================================================================
    # Final interval table
    # =========================================================================

    def populate_adjudication_table(self) -> None:
        """
        Populate the read-only table from the provisional final timeline.
        """
        started = perf_counter()

        try:
            self._populate_adjudication_table_impl()
        except Exception as exc:
            print("[ADJ-UI] Table population failed:", repr(exc))
            raise
        finally:
            self._adjudication_perf_log(
                "populate_adjudication_table",
                perf_counter() - started,
            )


    def _populate_adjudication_table_impl(self) -> None:
        """Populate table cells without changing final interval data."""
        comparison = self.adjudication_comparison
        intervals = (
            comparison.prefilled_intervals
            if comparison is not None
            else []
        )

        table = self.adjudication_table
        blocked = table.blockSignals(True)

        try:
            table.setRowCount(len(intervals))

            for row_index, interval in enumerate(intervals):
                values = (
                    interval.cpr,
                    interval.rhythm_label,
                    interval.rhythm_expl,
                    repr(float(interval.start)),
                    repr(float(interval.end)),
                )

                for column_index, value in enumerate(values):
                    table.setItem(
                        row_index,
                        column_index,
                        QTableWidgetItem(str(value)),
                    )
        finally:
            table.blockSignals(blocked)


    # =========================================================================
    # Selection helpers
    # =========================================================================

    def _find_final_interval_index(
        self,
        time_value: float,
    ) -> Optional[int]:
        """Find a final interval covering an absolute epoch coordinate."""
        comparison = self.adjudication_comparison

        if comparison is None:
            return None

        intervals = comparison.prefilled_intervals

        for index, interval in enumerate(intervals):
            if interval.start <= time_value < interval.end:
                return index

            if (
                index == len(intervals) - 1
                and time_value == interval.end
            ):
                return index

        return None


    def _clear_adjudication_selection_graphics(self) -> None:
        """Remove temporary selection highlighting from plots."""
        for plot, item in self.adjudication_selection_graphics:
            plot.removeItem(item)

        self.adjudication_selection_graphics = []


    def _highlight_adjudication_range(
        self,
        start: float,
        end: float,
    ) -> None:
        """
        Highlight a selected time range without changing annotation data.

        Highlighting appears on waveform plots and the final timeline.
        """
        self._clear_adjudication_selection_graphics()

        plots = self.adjudication_waveform_plots + [
            self.adjudication_timeline_plots["Final Adjudication"]
        ]

        for plot in plots:
            highlight = pg.LinearRegionItem(
                values=[float(start), float(end)],
                movable=False,
                brush=pg.mkBrush(255, 203, 5, 35),
                pen=pg.mkPen("#FFCB05", width=2),
            )
            highlight.setZValue(500)

            plot.addItem(highlight, ignoreBounds=True)
            self.adjudication_selection_graphics.append(
                (plot, highlight)
            )


    def _format_adjudication_source_label(
        self,
        annotation: Any,
    ) -> str:
        """Describe one source interval without exposing its username."""
        if annotation is None:
            return "No coverage"

        rhythm = annotation.rhythm_label or "Not applicable"
        explanation = annotation.rhythm_expl or "None"

        return (
            f"CPR: {annotation.cpr or 'Missing'}\n"
            f"Rhythm: {rhythm}\n"
            f"Explanation: {explanation}"
        )


    def _show_adjudication_region_details(
        self,
        region: Any,
    ) -> None:
        """Display both source decisions and comparison reasons."""
        reasons = (
            ", ".join(reason.replace("_", " ") for reason in region.reasons)
            or "No disagreement detected"
        )

        self.adjudication_comparison_details.setText(
            f"Annotator A\n"
            f"{self._format_adjudication_source_label(region.annotation_a)}\n\n"
            f"Annotator B\n"
            f"{self._format_adjudication_source_label(region.annotation_b)}\n\n"
            f"Comparison: {region.status.value.replace('_', ' ')}\n"
            f"Reasons: {reasons}"
        )


    # =========================================================================
    # Final interval selection
    # =========================================================================

    def select_adjudication_interval(
        self,
        interval_index: int,
    ) -> None:
        """
        Select a provisional final interval and display its current labels.

        Selection does not edit the interval or resolve a disagreement.
        """
        started = perf_counter()

        try:
            self._select_adjudication_interval_impl(interval_index)
        except Exception as exc:
            print("[ADJ-UI] Interval selection failed:", repr(exc))
            self.show_adjudication_error(
                "Interval Selection Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "select_adjudication_interval",
                perf_counter() - started,
            )


    def _select_adjudication_interval_impl(
        self,
        interval_index: int,
    ) -> None:
        """Update sidebar and selection graphics for one final interval."""
        comparison = self.adjudication_comparison

        if comparison is None:
            return

        intervals = comparison.prefilled_intervals

        if not 0 <= interval_index < len(intervals):
            return

        interval = intervals[interval_index]
        self.adjudication_selected_interval_index = interval_index
        self.adjudication_selected_region_id = None

        # Block question signals while displaying the current interval values.
        widgets = (
            self.adjudication_cpr_dropdown,
            self.adjudication_rhythm_dropdown,
            self.adjudication_explanation,
        )
        previous_blocks = [
            widget.blockSignals(True)
            for widget in widgets
        ]

        try:
            self.adjudication_cpr_dropdown.setCurrentText(interval.cpr)
            self.adjudication_rhythm_dropdown.setCurrentText(
                interval.rhythm_label
            )
            self.adjudication_explanation.setPlainText(
                interval.rhythm_expl
            )
        finally:
            for widget, blocked in zip(widgets, previous_blocks):
                widget.blockSignals(blocked)

        self.adjudication_selection_label.setText(
            f"Final interval {interval_index + 1} of {len(intervals)}\n"
            f"Start: {interval.start:.6f}\n"
            f"End: {interval.end:.6f}\n"
            f"Duration: {interval.duration:.3f} seconds"
        )

        midpoint = interval.start + interval.duration / 2.0

        for region in comparison.comparison_regions:
            if region.start <= midpoint < region.end:
                self.adjudication_selected_region_id = region.region_id
                self._show_adjudication_region_details(region)
                break

        self._highlight_adjudication_range(
            interval.start,
            interval.end,
        )

        table = self.adjudication_table
        blocked = table.blockSignals(True)

        try:
            table.selectRow(interval_index)
        finally:
            table.blockSignals(blocked)

        self.update_adjudication_label_controls()
        self.update_adjudication_navigation_controls()
        self.update_adjudication_boundary_controls()


    def handle_adjudication_table_selection(self) -> None:
        """Select the final interval corresponding to the selected table row."""
        row_index = self.adjudication_table.currentRow()

        if row_index >= 0:
            self.select_adjudication_interval(row_index)


    def handle_adjudication_timeline_click(
        self,
        track_name: str,
        mouse_event: Any,
    ) -> None:
        """
        Select a final interval or place a pending boundary on the final timeline.

        Source and comparison tracks remain read-only.
        """
        if mouse_event.button() != Qt.LeftButton:
            return

        comparison = self.adjudication_comparison

        if comparison is None:
            return

        plot = self.adjudication_timeline_plots[track_name]
        view_box = plot.getViewBox()

        if not view_box.sceneBoundingRect().contains(mouse_event.scenePos()):
            return

        point = view_box.mapSceneToView(mouse_event.scenePos())
        clicked_time = float(point.x())

        if self.adjudication_pending_split_index is not None:
            # While placement is active, do not change the selected target.
            if track_name == "Final Adjudication":
                self.place_adjudication_boundary(clicked_time)
            return

        interval_index = self._find_final_interval_index(clicked_time)

        if interval_index is not None:
            self.select_adjudication_interval(interval_index)

        for region in comparison.comparison_regions:
            if region.start <= clicked_time < region.end:
                self.adjudication_selected_region_id = region.region_id
                self._show_adjudication_region_details(region)
                break

        self.update_adjudication_navigation_controls()


    # =========================================================================
    # Unresolved-region navigation
    # =========================================================================

    def update_adjudication_navigation_controls(self) -> None:
        """
        Update unresolved navigation and explicit-resolution availability.
        """
        comparison = self.adjudication_comparison

        unresolved = (
            comparison.unresolved_regions
            if comparison is not None
            else []
        )

        count = len(unresolved)

        self.adjudication_previous_btn.setEnabled(count > 0)
        self.adjudication_next_btn.setEnabled(count > 0)

        selected_region = next(
            (
                region
                for region in comparison.comparison_regions
                if region.region_id == self.adjudication_selected_region_id
            ),
            None,
        ) if comparison is not None else None

        self.adjudication_resolve_btn.setEnabled(
            selected_region is not None
            and selected_region.requires_resolution
            and not selected_region.resolved
        )

        current_position = next(
            (
                index + 1
                for index, region in enumerate(unresolved)
                if region.region_id == self.adjudication_selected_region_id
            ),
            None,
        )

        self.adjudication_progress_label.setText(
            f"Unresolved region {current_position} of {count}"
            if current_position is not None
            else f"Unresolved regions: {count}"
        )

        if getattr(self, "adjudication_complete", False):
            self.apply_adjudication_read_only_state()


    def navigate_adjudication_unresolved(
        self,
        direction: int,
    ) -> None:
        """
        Navigate to the previous or next unresolved comparison region.

        Parameters
        ----------
        direction : int
            Positive values move forward; negative values move backward.

        Notes
        -----
        Navigation wraps at either end. It never marks a region resolved.
        """
        started = perf_counter()

        try:
            self._navigate_adjudication_unresolved_impl(direction)
        except Exception as exc:
            print("[ADJ-UI] Unresolved navigation failed:", repr(exc))
            self.show_adjudication_error(
                "Navigation Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "navigate_adjudication_unresolved",
                perf_counter() - started,
            )


    def _navigate_adjudication_unresolved_impl(
        self,
        direction: int,
    ) -> None:
        """Select and center an unresolved region without changing labels."""
        comparison = self.adjudication_comparison

        if comparison is None:
            return

        unresolved = comparison.unresolved_regions

        if not unresolved:
            self.update_adjudication_navigation_controls()
            return

        current_index = next(
            (
                index
                for index, region in enumerate(unresolved)
                if region.region_id == self.adjudication_selected_region_id
            ),
            None,
        )

        if current_index is None:
            target_index = 0 if direction >= 0 else len(unresolved) - 1
        else:
            step = 1 if direction >= 0 else -1
            target_index = (current_index + step) % len(unresolved)

        region = unresolved[target_index]
        midpoint = region.start + region.duration / 2.0

        interval_index = self._find_final_interval_index(midpoint)

        if interval_index is not None:
            self.select_adjudication_interval(interval_index)

        self.adjudication_selected_region_id = region.region_id
        self._show_adjudication_region_details(region)
        self._highlight_adjudication_range(region.start, region.end)

        # Show context before and after the disagreement without changing data.
        margin = max(2.0, region.duration * 0.1)
        left = max(
            self.adjudication_waveform_start,
            region.start - margin,
        )
        right = min(
            self.adjudication_waveform_end,
            region.end + margin,
        )

        if right > left:
            self.adjudication_waveform_plots[0].setXRange(
                left,
                right,
                padding=0,
            )

        self.update_adjudication_navigation_controls()


    # =========================================================================
    # Final label editing and validation
    # =========================================================================

    def get_adjudication_label_errors(
        self,
        cpr: str,
        rhythm: str,
        explanation: str,
    ) -> list[str]:
        """
        Validate final-label fields using the existing annotation question rules.

        Comments are optional except for CPR Unable to Determine and rhythm
        Other/Unable to Determine.
        """
        errors: list[str] = []

        if cpr not in {"Yes", "No", "Unable to Determine"}:
            errors.append("Select a CPR answer.")
            return errors

        if cpr == "No":
            if not rhythm:
                errors.append("Select a rhythm.")

            if (
                rhythm in {"Other", "Unable to Determine"}
                and not explanation.strip()
            ):
                errors.append("An explanation is required for this rhythm.")

        elif cpr == "Unable to Determine" and not explanation.strip():
            errors.append(
                "An explanation is required for CPR Unable to Determine."
            )

        return errors


    def update_adjudication_label_controls(
        self,
        *args: Any,
    ) -> None:
        """
        Enable final-label controls according to the selected interval and CPR.

        This updates UI availability only. It does not modify saved interval data.
        """
        if getattr(self, "adjudication_complete", False):
            self.apply_adjudication_read_only_state()
            return

        comparison = self.adjudication_comparison
        selected_index = self.adjudication_selected_interval_index

        has_selection = (
            comparison is not None
            and selected_index is not None
            and 0 <= selected_index < len(comparison.prefilled_intervals)
        )

        self.adjudication_cpr_dropdown.setEnabled(has_selection)

        if not has_selection:
            self.adjudication_rhythm_dropdown.setEnabled(False)
            self.adjudication_explanation.setEnabled(False)
            self.adjudication_apply_btn.setEnabled(False)
            return

        cpr = self.adjudication_cpr_dropdown.currentText().strip()

        self.adjudication_rhythm_dropdown.setEnabled(cpr == "No")

        if cpr != "No":
            # CPR Yes/Unable to Determine does not have a rhythm label.
            blocked = self.adjudication_rhythm_dropdown.blockSignals(True)
            self.adjudication_rhythm_dropdown.setCurrentIndex(0)
            self.adjudication_rhythm_dropdown.blockSignals(blocked)

        self.adjudication_explanation.setEnabled(
            cpr in {"Yes", "No", "Unable to Determine"}
        )

        rhythm = self.adjudication_rhythm_dropdown.currentText().strip()

        explanation_required = (
            cpr == "Unable to Determine"
            or (
                cpr == "No"
                and rhythm in {"Other", "Unable to Determine"}
            )
        )

        self.adjudication_explanation.setPlaceholderText(
            "Required explanation."
            if explanation_required
            else "Optional interval comment."
        )

        errors = self.get_adjudication_label_errors(
            cpr,
            rhythm,
            self.adjudication_explanation.toPlainText(),
        )

        self.adjudication_apply_btn.setEnabled(not errors)
        self.adjudication_apply_btn.setToolTip(
            "\n".join(errors)
            if errors
            else "Apply these values to the selected final interval."
        )


    def apply_adjudication_final_label(self) -> None:
        """
        Apply the sidebar values to the selected final interval.

        Applying a label does not resolve a disagreement. Previously resolved
        regions overlapping a changed interval become unresolved again.
        """
        started = perf_counter()

        try:
            self._apply_adjudication_final_label_impl()
        except Exception as exc:
            print("[ADJ-UI] Applying final label failed:", repr(exc))
            self.show_adjudication_error(
                "Apply Final Label Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "apply_adjudication_final_label",
                perf_counter() - started,
            )


    def _apply_adjudication_final_label_impl(self) -> None:
        """Validate and apply final-label changes without writing any files."""
        comparison = self.adjudication_comparison
        index = self.adjudication_selected_interval_index

        if comparison is None or index is None:
            raise ValueError("Select a final interval first.")

        if not 0 <= index < len(comparison.prefilled_intervals):
            raise ValueError("The selected final interval is unavailable.")

        interval = comparison.prefilled_intervals[index]

        cpr = self.adjudication_cpr_dropdown.currentText().strip()
        rhythm = (
            self.adjudication_rhythm_dropdown.currentText().strip()
            if cpr == "No"
            else ""
        )
        explanation = self.adjudication_explanation.toPlainText().strip()

        errors = self.get_adjudication_label_errors(
            cpr,
            rhythm,
            explanation,
        )

        if errors:
            raise ValueError("\n".join(errors))

        old_values = (
            interval.cpr,
            interval.rhythm_label,
            interval.rhythm_expl,
        )
        new_values = (cpr, rhythm, explanation)

        if old_values == new_values:
            self.adjudication_status_label.setText(
                "No label changes to apply."
            )
            return

        interval.cpr = cpr
        interval.rhythm_label = rhythm
        interval.rhythm_expl = explanation
        interval.adjudication_updated_at = utc_now_iso()

        # Invalidate only resolved regions affected by this final interval.
        for region in comparison.comparison_regions:
            overlaps = (
                interval.start < region.end
                and interval.end > region.start
            )

            if overlaps and region.resolved:
                region.resolved = False
                region.resolved_at = None

                if region.status == ComparisonStatus.RESOLVED_DISAGREEMENT:
                    region.status = (
                        ComparisonStatus.MISSING_COVERAGE
                        if "missing_coverage" in region.reasons
                        else ComparisonStatus.UNRESOLVED_DISAGREEMENT
                    )

        self.adjudication_dirty = True

        # Retain the selected comparison region when refreshing the display.
        selected_region_id = self.adjudication_selected_region_id

        self._clear_adjudication_selection_graphics()
        self.draw_adjudication_timelines()
        self.populate_adjudication_table()
        self.select_adjudication_interval(index)

        if selected_region_id is not None:
            for region in comparison.comparison_regions:
                if region.region_id == selected_region_id:
                    self.adjudication_selected_region_id = selected_region_id
                    self._show_adjudication_region_details(region)
                    break

        self.update_adjudication_navigation_controls()

        self.adjudication_status_label.setText(
            "Final label applied in memory. "
            "Click Mark Resolved separately when the review is finished. "
            "Saving is not implemented yet."
        )


    # =========================================================================
    # Finalization
    # =========================================================================

    def finalize_current_adjudication(self) -> None:
        """
        Validate, request terminal metadata, and save completed adjudication.

        The window becomes read-only only after the completed files are verified.
        """
        started = perf_counter()

        try:
            self._finalize_current_adjudication_impl()
        except Exception as exc:
            print("[ADJ-UI] Finalization failed:", repr(exc))
            self.adjudication_save_status.setText("Finalization failed.")
            self.adjudication_save_status.setToolTip(str(exc))
            self.show_adjudication_error(
                "Cannot Finalize Adjudication",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "finalize_current_adjudication",
                perf_counter() - started,
            )


    def _finalize_current_adjudication_impl(self) -> None:
        """Finalize the loaded session without touching annotator files."""
        comparison = self.adjudication_comparison
        record = getattr(self, "adjudication_loaded_record", None)

        if comparison is None or not isinstance(record, dict):
            raise ValueError("Load an adjudication first.")

        if self.adjudication_complete:
            raise ValueError("This adjudication is already complete.")

        if self.adjudication_pending_split_index is not None:
            raise ValueError("Finish or cancel boundary placement first.")

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError("Apply the pending final-label changes first.")

        errors = validate_adjudication_for_finalization(
            comparison,
            self.adjudication_waveform_start,
            self.adjudication_waveform_end,
        )

        if errors:
            raise ValueError("\n".join(errors))

        options = [
            "Cardiac arrest/event does NOT continue beyond waveform",
            "Cardiac arrest/event CONTINUES beyond waveform",
        ]

        status_dialog = QInputDialog(self)
        status_dialog.setWindowTitle("Finalize Adjudication")
        status_dialog.setLabelText(
            "Select the final terminal-event decision:"
        )
        status_dialog.setComboBoxItems(options)
        status_dialog.setComboBoxEditable(False)
        status_dialog.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
            }
            QLabel, QComboBox {
                color: #00274C;
                background-color: #FFFFFF;
            }
            QPushButton {
                background-color: #00274C;
                color: #FFCB05;
            }
            """
        )

        if not status_dialog.exec_():
            return

        terminal_status = (
            "continues_beyond_waveform"
            if status_dialog.textValue() == options[1]
            else "does_not_continue_beyond_waveform"
        )

        comment_dialog = QInputDialog(self)
        comment_dialog.setWindowTitle("Final Comment")
        comment_dialog.setLabelText("Optional final comment:")
        comment_dialog.setOption(QInputDialog.UsePlainTextEditForTextInput)
        comment_dialog.setStyleSheet(status_dialog.styleSheet())

        if not comment_dialog.exec_():
            return

        terminal_comment = comment_dialog.textValue().strip()

        # Archive the prior completed output before creating a revised completion.
        if self.adjudication_reopened_from_complete:
            self._save_current_adjudication_draft_impl()

        path = save_completed_adjudication(
            record,
            comparison,
            waveform_start=self.adjudication_waveform_start,
            waveform_end=self.adjudication_waveform_end,
            terminal_event_status=terminal_status,
            terminal_event_comment=terminal_comment,
        )

        # Update live state only after persistence succeeds.
        for interval in comparison.prefilled_intervals:
            interval.waveform_complete = False
            interval.terminal_event_status = ""
            interval.terminal_event_comment = ""

        final_interval = comparison.prefilled_intervals[-1]
        final_interval.waveform_complete = True
        final_interval.terminal_event_status = terminal_status
        final_interval.terminal_event_comment = terminal_comment

        self.adjudication_complete = True
        self.adjudication_dirty = False

        self.populate_adjudication_table()
        self.apply_adjudication_read_only_state()

        self.adjudication_status_label.setText(
            "Adjudication finalized. Final intervals are read-only."
        )
        self.adjudication_save_status.setText(
            "Completed adjudication saved."
        )
        self.adjudication_save_status.setToolTip(str(path))


    def apply_adjudication_read_only_state(self) -> None:
        """
        Disable editing and saving controls after successful finalization.

        Plot navigation and table inspection remain available.
        """
        if not self.adjudication_complete:
            return

        for widget in (
            self.adjudication_cpr_dropdown,
            self.adjudication_rhythm_dropdown,
            self.adjudication_explanation,
            self.adjudication_apply_btn,
            self.adjudication_add_boundary_btn,
            self.adjudication_remove_boundary_btn,
            self.adjudication_resolve_btn,
            self.adjudication_save_btn,
            self.adjudication_finalize_btn,
        ):
            widget.setEnabled(False)

        for line in self.adjudication_boundary_lines:
            line.setMovable(False)

        self.adjudication_reopen_btn.setEnabled(True)


    # =========================================================================
    # Explicit disagreement resolution
    # =========================================================================

    def get_adjudication_region_resolution_errors(
        self,
        region: Any,
    ) -> list[str]:
        """
        Check that valid final labels cover the entire selected review region.

        Coverage is checked independently from source annotator agreement.
        """
        comparison = self.adjudication_comparison

        if comparison is None:
            return ["No comparison is loaded."]

        cursor = float(region.start)
        errors: list[str] = []

        intervals = sorted(
            comparison.prefilled_intervals,
            key=lambda interval: interval.start,
        )

        for interval in intervals:
            if interval.end <= region.start or interval.start >= region.end:
                continue

            overlap_start = max(interval.start, region.start)
            overlap_end = min(interval.end, region.end)

            if overlap_start > cursor + 1e-6:
                errors.append("Final timeline has a gap in this review region.")

            if overlap_start < cursor - 1e-6:
                errors.append("Final timeline has an overlap in this review region.")

            label_errors = self.get_adjudication_label_errors(
                interval.cpr,
                interval.rhythm_label,
                interval.rhythm_expl,
            )

            errors.extend(label_errors)
            cursor = max(cursor, overlap_end)

        if cursor < region.end - 1e-6:
            errors.append("Final labels do not cover the entire review region.")

        # Remove repeated messages while preserving their order.
        return list(dict.fromkeys(errors))


    def mark_adjudication_region_resolved(self) -> None:
        """
        Explicitly resolve the selected disagreement after validating final labels.

        Unapplied sidebar edits must be applied first.
        """
        started = perf_counter()

        try:
            self._mark_adjudication_region_resolved_impl()
        except Exception as exc:
            print("[ADJ-UI] Resolution failed:", repr(exc))
            self.show_adjudication_error(
                "Cannot Mark Resolved",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "mark_adjudication_region_resolved",
                perf_counter() - started,
            )


    def _mark_adjudication_region_resolved_impl(self) -> None:
        """Validate and resolve one selected comparison region."""
        comparison = self.adjudication_comparison
        region_id = self.adjudication_selected_region_id
        interval_index = self.adjudication_selected_interval_index

        if comparison is None or region_id is None:
            raise ValueError("Select an unresolved comparison region first.")

        region = next(
            (
                item
                for item in comparison.comparison_regions
                if item.region_id == region_id
            ),
            None,
        )

        if region is None or not region.requires_resolution:
            raise ValueError("The selected region does not require resolution.")

        if interval_index is not None:
            interval = comparison.prefilled_intervals[interval_index]

            sidebar_cpr = self.adjudication_cpr_dropdown.currentText().strip()
            sidebar_rhythm = (
                self.adjudication_rhythm_dropdown.currentText().strip()
                if sidebar_cpr == "No"
                else ""
            )
            sidebar_explanation = (
                self.adjudication_explanation.toPlainText().strip()
            )

            if (
                sidebar_cpr,
                sidebar_rhythm,
                sidebar_explanation,
            ) != (
                interval.cpr,
                interval.rhythm_label,
                interval.rhythm_expl,
            ):
                raise ValueError(
                    "Click Apply Final Label before marking this region resolved."
                )

        errors = self.get_adjudication_region_resolution_errors(region)

        if errors:
            raise ValueError("\n".join(errors))

        region.resolved = True
        region.resolved_at = utc_now_iso()
        region.status = ComparisonStatus.RESOLVED_DISAGREEMENT

        self.adjudication_dirty = True

        self._clear_adjudication_selection_graphics()
        self.draw_adjudication_timelines()
        self._highlight_adjudication_range(region.start, region.end)
        self._show_adjudication_region_details(region)
        self.update_adjudication_navigation_controls()

        self.adjudication_status_label.setText(
            "Region explicitly marked resolved. Changes are in memory only; "
            "saving is not implemented yet."
        )


    # =========================================================================
    # Final timeline boundary dragging
    # =========================================================================

    def refresh_adjudication_after_structure_change(
        self,
        selected_index: int,
    ) -> None:
        """
        Refresh final graphics and selection after splitting or merging intervals.

        This function does not modify source annotations or write files.
        """
        self._clear_adjudication_selection_graphics()
        self.draw_adjudication_timelines()
        self.populate_adjudication_table()

        self.adjudication_selected_interval_index = None
        self.adjudication_selected_region_id = None

        self.select_adjudication_interval(selected_index)
        self.update_adjudication_navigation_controls()
        self.update_adjudication_boundary_controls()


    def update_adjudication_boundary_controls(self) -> None:
        """
        Enable boundary controls according to selection and placement mode.
        """
        if getattr(self, "adjudication_complete", False):
            self.apply_adjudication_read_only_state()
            return

        if self.adjudication_pending_split_index is not None:
            self.adjudication_add_boundary_btn.setEnabled(True)
            self.adjudication_add_boundary_btn.setText("Cancel Add")
            self.adjudication_remove_boundary_btn.setEnabled(False)
            return

        self.adjudication_add_boundary_btn.setText("Add Boundary")

        comparison = self.adjudication_comparison
        index = self.adjudication_selected_interval_index

        has_selection = (
            comparison is not None
            and index is not None
            and 0 <= index < len(comparison.prefilled_intervals)
        )

        if not has_selection:
            self.adjudication_add_boundary_btn.setEnabled(False)
            self.adjudication_remove_boundary_btn.setEnabled(False)
            return

        interval = comparison.prefilled_intervals[index]

        self.adjudication_add_boundary_btn.setEnabled(
            interval.duration >= 2.0 * MINIMUM_VALID_INTERVAL_SEC
        )
        self.adjudication_remove_boundary_btn.setEnabled(
            index < len(comparison.prefilled_intervals) - 1
        )

        self.adjudication_add_boundary_btn.setToolTip(
            "Click this button, then click a waveform or the final timeline "
            "to split the selected interval."
        )
        self.adjudication_remove_boundary_btn.setToolTip(
            "Remove the boundary after the selected interval and merge "
            "it with the next interval."
        )


    def add_adjudication_boundary(self) -> None:
        """
        Activate or cancel click-to-place boundary insertion.

        The selected final interval remains the split target until placement
        succeeds or the reviewer cancels.
        """
        started = perf_counter()

        try:
            self._add_adjudication_boundary_impl()
        except Exception as exc:
            print("[ADJ-UI] Add boundary failed:", repr(exc))
            self.show_adjudication_error(
                "Add Boundary Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "add_adjudication_boundary",
                perf_counter() - started,
            )


    def _add_adjudication_boundary_impl(self) -> None:
        """Arm boundary placement without changing final interval data."""
        if self.adjudication_pending_split_index is not None:
            self.cancel_adjudication_boundary_placement()
            return

        comparison = self.adjudication_comparison
        index = self.adjudication_selected_interval_index

        if comparison is None or index is None:
            raise ValueError("Select a final interval first.")

        if not 0 <= index < len(comparison.prefilled_intervals):
            raise ValueError("The selected final interval is unavailable.")

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Apply the pending label changes before adding a boundary."
            )

        interval = comparison.prefilled_intervals[index]
        minimum = float(MINIMUM_VALID_INTERVAL_SEC)

        if minimum <= 0:
            raise ValueError(
                "Boundary insertion requires a positive minimum interval duration."
            )

        if interval.duration < 2.0 * minimum:
            raise ValueError(
                f"The selected interval must be at least "
                f"{2.0 * minimum:g} seconds long to split."
            )

        self.adjudication_pending_split_index = index
        self.adjudication_add_boundary_btn.setText("Cancel Add")

        # Prevent other editing operations from changing the armed target.
        self.adjudication_remove_boundary_btn.setEnabled(False)

        for line in self.adjudication_boundary_lines:
            line.setMovable(False)

        self.adjudication_status_label.setText(
            "Click a waveform or the Final Adjudication timeline inside the "
            "selected interval to add a boundary. Click Cancel Add to cancel."
        )


    def cancel_adjudication_boundary_placement(self) -> None:
        """
        Cancel pending boundary insertion without changing final intervals.
        """
        self.adjudication_pending_split_index = None
        self.adjudication_add_boundary_btn.setText("Add Boundary")

        self.draw_adjudication_boundary_handles()
        self.update_adjudication_boundary_controls()

        self.adjudication_status_label.setText(
            "Boundary placement cancelled."
        )


    def remove_adjudication_boundary(self) -> None:
        """
        Merge adjacent final intervals with timing and visible error handling.
        """
        started = perf_counter()

        try:
            self._remove_adjudication_boundary_impl()
        except Exception as exc:
            print("[ADJ-UI] Remove boundary failed:", repr(exc))
            self.show_adjudication_error(
                "Remove Boundary Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "remove_adjudication_boundary",
                perf_counter() - started,
            )


    def place_adjudication_boundary(
        self,
        time_value: float,
    ) -> None:
        """
        Split the armed final interval at a clicked absolute epoch coordinate.

        Both new intervals inherit the existing final label. This operation does
        not modify source annotations or automatically resolve review regions.
        """
        started = perf_counter()

        try:
            self._place_adjudication_boundary_impl(time_value)
        except Exception as exc:
            print("[ADJ-UI] Boundary placement failed:", repr(exc))
            self.show_adjudication_error(
                "Boundary Placement Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "place_adjudication_boundary",
                perf_counter() - started,
            )


    def _place_adjudication_boundary_impl(
        self,
        time_value: float,
    ) -> None:
        """Validate the clicked position and commit a contiguous interval split."""
        comparison = self.adjudication_comparison
        index = self.adjudication_pending_split_index

        if comparison is None or index is None:
            return

        if not 0 <= index < len(comparison.prefilled_intervals):
            self.cancel_adjudication_boundary_placement()
            raise ValueError("The interval selected for splitting is unavailable.")

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Apply pending label changes before placing the boundary."
            )

        split_time = float(time_value)

        if not np.isfinite(split_time):
            raise ValueError("The clicked boundary time is not finite.")

        interval = comparison.prefilled_intervals[index]
        minimum = float(MINIMUM_VALID_INTERVAL_SEC)

        lower = float(interval.start + minimum)
        upper = float(interval.end - minimum)

        if split_time < lower or split_time > upper:
            # Keep placement active so the reviewer can try another position.
            raise ValueError(
                "Click inside the selected interval, leaving at least "
                f"{minimum:g} second(s) on each side."
            )

        updated_at = utc_now_iso()

        left = replace(
            interval,
            end=split_time,
            waveform_complete=False,
            terminal_event_status="",
            terminal_event_comment="",
            adjudication_updated_at=updated_at,
        )

        right = replace(
            interval,
            start=split_time,
            adjudication_updated_at=updated_at,
        )

        # Replace only final adjudication data; original source intervals are intact.
        comparison.prefilled_intervals[index:index + 1] = [left, right]

        self.invalidate_adjudication_resolutions_in_range(
            interval.start,
            interval.end,
        )

        self.adjudication_pending_split_index = None
        self.adjudication_add_boundary_btn.setText("Add Boundary")
        self.adjudication_dirty = True

        self.refresh_adjudication_after_structure_change(index)

        self.adjudication_status_label.setText(
            "Boundary added at the clicked position. Both intervals inherited "
            "the previous final label. Save Draft to preserve the change."
        )
        self.adjudication_save_status.setText(
            "Unsaved boundary changes."
        )


    def handle_adjudication_waveform_click(
        self,
        row_index: int,
        mouse_event: Any,
    ) -> None:
        """
        Place a pending boundary from a waveform click.

        Ordinary waveform clicks are otherwise left unchanged.
        """
        if mouse_event.button() != Qt.LeftButton:
            return

        if self.adjudication_pending_split_index is None:
            return

        plot = self.adjudication_waveform_plots[row_index]
        view_box = plot.getViewBox()

        if not view_box.sceneBoundingRect().contains(mouse_event.scenePos()):
            return

        point = view_box.mapSceneToView(mouse_event.scenePos())

        # Scene-to-view conversion returns absolute epoch coordinates, not the
        # relative seconds displayed by the axis.
        self.place_adjudication_boundary(float(point.x()))


    def _remove_adjudication_boundary_impl(self) -> None:
        """
        Remove the boundary after the selected interval.

        Identical labels are retained. Different labels or explanations are
        cleared after explicit confirmation so neither interval is favored.
        """
        comparison = self.adjudication_comparison
        index = self.adjudication_selected_interval_index

        if comparison is None or index is None:
            raise ValueError("Select a final interval first.")

        intervals = comparison.prefilled_intervals

        if not 0 <= index < len(intervals) - 1:
            raise ValueError(
                "Select an interval with a following interval. "
                "The final endpoint cannot be removed."
            )

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Apply the pending label changes before removing a boundary."
            )

        left = intervals[index]
        right = intervals[index + 1]

        if abs(left.end - right.start) > 1e-6:
            raise ValueError("The selected intervals are not contiguous.")

        labels_match = (
            left.cpr,
            left.rhythm_label,
            left.rhythm_expl,
        ) == (
            right.cpr,
            right.rhythm_label,
            right.rhythm_expl,
        )

        if not labels_match:
            # Explicit confirmation prevents silent loss of competing final labels.
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Merge Different Final Labels")
            dialog.setIcon(QMessageBox.Question)
            dialog.setText(
                "These intervals have different labels or comments."
            )
            dialog.setInformativeText(
                "Removing the boundary will merge them and clear the final "
                "CPR, rhythm, and explanation. You must assign a new label."
            )
            dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            dialog.setDefaultButton(QMessageBox.Cancel)
            dialog.setStyleSheet(
                """
                QMessageBox {
                    background-color: #FFFFFF;
                }
                QMessageBox QLabel {
                    color: #00274C;
                    background-color: #FFFFFF;
                }
                QMessageBox QPushButton {
                    background-color: #00274C;
                    color: #FFCB05;
                    padding: 6px 12px;
                }
                """
            )

            if dialog.exec_() != QMessageBox.Yes:
                return

        merged = replace(
            left,
            end=float(right.end),
            cpr=left.cpr if labels_match else "",
            rhythm_label=left.rhythm_label if labels_match else "",
            rhythm_expl=left.rhythm_expl if labels_match else "",
            # Terminal metadata belongs to the last interval in the merged range.
            waveform_complete=right.waveform_complete,
            terminal_event_status=right.terminal_event_status,
            terminal_event_comment=right.terminal_event_comment,
            adjudication_updated_at=utc_now_iso(),
        )

        intervals[index:index + 2] = [merged]

        self.invalidate_adjudication_resolutions_in_range(
            merged.start,
            merged.end,
        )

        self.adjudication_dirty = True
        self.refresh_adjudication_after_structure_change(index)

        self.adjudication_status_label.setText(
            "Boundary removed; neighboring intervals merged."
            if labels_match
            else "Boundary removed. Assign a final label to the merged interval."
        )
        self.adjudication_save_status.setText("Unsaved boundary changes.")


    def draw_adjudication_boundary_handles(self) -> None:
        """
        Draw draggable internal boundaries on the final adjudication timeline.

        Source timelines remain read-only. The first start and final end are fixed.
        """
        started = perf_counter()

        try:
            self._draw_adjudication_boundary_handles_impl()
        except Exception as exc:
            print("[ADJ-UI] Boundary handle drawing failed:", repr(exc))
            raise
        finally:
            self._adjudication_perf_log(
                "draw_adjudication_boundary_handles",
                perf_counter() - started,
            )


    def _draw_adjudication_boundary_handles_impl(self) -> None:
        """Create one handle for each shared internal final-interval boundary."""
        plot = self.adjudication_timeline_plots["Final Adjudication"]

        # Previous handles may already have been removed by plot.clear().
        for line in getattr(self, "adjudication_boundary_lines", []):
            if line.scene() is not None:
                plot.removeItem(line)

        self.adjudication_boundary_lines = []

        comparison = self.adjudication_comparison

        if comparison is None:
            return

        intervals = comparison.prefilled_intervals

        for left_index in range(len(intervals) - 1):
            left = intervals[left_index]
            right = intervals[left_index + 1]

            # Comparison fragments can already be shorter than the final minimum.
            # Permit those existing fragments, but do not shrink them further.
            left_minimum = min(
                MINIMUM_VALID_INTERVAL_SEC,
                left.duration,
            )
            right_minimum = min(
                MINIMUM_VALID_INTERVAL_SEC,
                right.duration,
            )

            lower_bound = left.start + left_minimum
            upper_bound = right.end - right_minimum

            if lower_bound > upper_bound:
                continue

            line = pg.InfiniteLine(
                pos=float(left.end),
                angle=90,
                movable=(
                    upper_bound > lower_bound
                    and not getattr(self, "adjudication_complete", False)
                ),
                bounds=[float(lower_bound), float(upper_bound)],
                pen=pg.mkPen("#00274C", width=2),
                hoverPen=pg.mkPen("#FFCB05", width=4),
            )
            line.setZValue(1000)

            # Capture the index explicitly; do not depend on the loop variable.
            line.sigPositionChangeFinished.connect(
                lambda moved_line, index=left_index:
                    self.finish_adjudication_boundary_drag(
                        index,
                        moved_line,
                    )
            )

            plot.addItem(line, ignoreBounds=True)
            self.adjudication_boundary_lines.append(line)


    def invalidate_adjudication_resolutions_in_range(
        self,
        start: float,
        end: float,
    ) -> None:
        """
        Return resolved comparison regions affected by a final edit to unresolved.

        Original source labels and comparison coordinates remain unchanged.
        """
        comparison = self.adjudication_comparison

        if comparison is None:
            return

        for region in comparison.comparison_regions:
            overlaps = start < region.end and end > region.start

            if not overlaps or not region.resolved:
                continue

            region.resolved = False
            region.resolved_at = None

            if region.status == ComparisonStatus.RESOLVED_DISAGREEMENT:
                region.status = (
                    ComparisonStatus.MISSING_COVERAGE
                    if "missing_coverage" in region.reasons
                    else ComparisonStatus.UNRESOLVED_DISAGREEMENT
                )


    def finish_adjudication_boundary_drag(
        self,
        left_index: int,
        line: pg.InfiniteLine,
    ) -> None:
        """
        Commit a dragged internal boundary with timing and visible error handling.

        A drag changes the two neighboring final intervals only. It does not save
        files or automatically resolve a disagreement.
        """
        started = perf_counter()

        try:
            self._finish_adjudication_boundary_drag_impl(
                left_index,
                line,
            )
        except Exception as exc:
            print("[ADJ-UI] Boundary movement failed:", repr(exc))

            # Restore handles to the unchanged interval data after a rejected drag.
            self.draw_adjudication_boundary_handles()

            self.show_adjudication_error(
                "Boundary Change Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "finish_adjudication_boundary_drag",
                perf_counter() - started,
            )


    def _finish_adjudication_boundary_drag_impl(
        self,
        left_index: int,
        line: pg.InfiniteLine,
    ) -> None:
        """Validate and commit the shared boundary between two final intervals."""
        comparison = self.adjudication_comparison

        if comparison is None:
            return

        intervals = comparison.prefilled_intervals

        if not 0 <= left_index < len(intervals) - 1:
            raise ValueError("The selected boundary is no longer available.")

        left = intervals[left_index]
        right = intervals[left_index + 1]
        original_time = float(left.end)

        # Do not discard sidebar edits when selecting the affected interval.
        if self.adjudication_sidebar_has_unapplied_changes():
            line.setValue(original_time)
            raise ValueError(
                "Apply the pending final-label changes before moving a boundary."
            )

        new_time = float(line.value())

        if not np.isfinite(new_time):
            line.setValue(original_time)
            raise ValueError("The boundary position is not finite.")

        left_minimum = min(
            MINIMUM_VALID_INTERVAL_SEC,
            left.duration,
        )
        right_minimum = min(
            MINIMUM_VALID_INTERVAL_SEC,
            right.duration,
        )

        lower_bound = float(left.start + left_minimum)
        upper_bound = float(right.end - right_minimum)

        # Clamp numerical edge effects to the same limits used by the handle.
        new_time = max(lower_bound, min(new_time, upper_bound))

        if not left.start < new_time < right.end:
            line.setValue(original_time)
            raise ValueError("Moving this boundary would collapse an interval.")

        if new_time == original_time:
            line.setValue(original_time)
            return

        # Commit both sides together so the final timeline remains contiguous.
        updated_at = utc_now_iso()

        left.end = new_time
        right.start = new_time
        left.adjudication_updated_at = updated_at
        right.adjudication_updated_at = updated_at

        # Both neighboring final intervals have changed coverage.
        self.invalidate_adjudication_resolutions_in_range(
            float(left.start),
            float(right.end),
        )

        self.adjudication_dirty = True

        self._clear_adjudication_selection_graphics()
        self.draw_adjudication_timelines()
        self.populate_adjudication_table()
        self.select_adjudication_interval(left_index)
        self.update_adjudication_navigation_controls()

        self.adjudication_status_label.setText(
            "Final boundary updated. Affected resolved regions require review "
            "again. Save Draft to preserve the change."
        )
        self.adjudication_save_status.setText("Unsaved boundary changes.")

    # =========================================================================
    # Unsaved-work protection
    # =========================================================================

    def confirm_discard_adjudication_changes(self) -> bool:
        """
        Ask before discarding applied or unapplied adjudication edits.
        """
        has_changes = (
            getattr(self, "adjudication_dirty", False)
            or self.adjudication_sidebar_has_unapplied_changes()
        )

        if not has_changes:
            return True

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Unsaved Adjudication")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText("This adjudication has unsaved changes.")
        dialog.setInformativeText(
            "Cancel to apply any pending label changes and save a draft, "
            "or discard the changes to continue."
        )
        dialog.setStandardButtons(
            QMessageBox.Discard | QMessageBox.Cancel
        )
        dialog.setDefaultButton(QMessageBox.Cancel)

        dialog.setStyleSheet(
            """
            QMessageBox {
                background-color: #FFFFFF;
            }
            QMessageBox QLabel {
                color: #00274C;
                background-color: #FFFFFF;
            }
            QMessageBox QPushButton {
                background-color: #00274C;
                color: #FFCB05;
                padding: 6px 12px;
            }
            """
        )

        return dialog.exec_() == QMessageBox.Discard


    # =========================================================================
    # Draft saving and resume
    # =========================================================================

    def adjudication_sidebar_has_unapplied_changes(self) -> bool:
        """
        Return whether the sidebar differs from the selected final interval.
        """
        comparison = self.adjudication_comparison
        index = self.adjudication_selected_interval_index

        if comparison is None or index is None:
            return False

        interval = comparison.prefilled_intervals[index]

        cpr = self.adjudication_cpr_dropdown.currentText().strip()
        rhythm = (
            self.adjudication_rhythm_dropdown.currentText().strip()
            if cpr == "No"
            else ""
        )
        explanation = self.adjudication_explanation.toPlainText().strip()

        return (cpr, rhythm, explanation) != (
            interval.cpr,
            interval.rhythm_label,
            interval.rhythm_expl,
        )


    def save_current_adjudication_draft(self) -> None:
        """Save the loaded reviewer session with timing and visible errors."""
        started = perf_counter()

        try:
            self._save_current_adjudication_draft_impl()
        except Exception as exc:
            print("[ADJ-UI] Save failed:", repr(exc))
            self.adjudication_save_status.setText(f"Save failed: {exc}")
            self.show_adjudication_error("Draft Save Failed", str(exc))
        finally:
            self._adjudication_perf_log(
                "save_current_adjudication_draft",
                perf_counter() - started,
            )


    def _save_current_adjudication_draft_impl(self) -> None:
        """
        Save the loaded reviewer session.

        The first save after reopening preserves the previous completed version
        in a history directory.
        """
        comparison = self.adjudication_comparison
        record = getattr(self, "adjudication_loaded_record", None)

        if comparison is None or not isinstance(record, dict):
            raise ValueError("Load an adjudication before saving.")

        if self.adjudication_complete:
            raise ValueError(
                "Reopen the completed adjudication before saving a draft."
            )

        if self.adjudication_pending_split_index is not None:
            raise ValueError(
                "Finish or cancel boundary placement before saving."
            )

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Click Apply Final Label before saving the sidebar changes."
            )

        if self.adjudication_reopened_from_complete:
            path = save_reopened_adjudication_draft(
                record,
                comparison,
                selected_interval_index=(
                    self.adjudication_selected_interval_index
                ),
                selected_region_id=self.adjudication_selected_region_id,
            )
        else:
            path = save_adjudication_draft(
                record,
                comparison,
                selected_interval_index=(
                    self.adjudication_selected_interval_index
                ),
                selected_region_id=self.adjudication_selected_region_id,
            )

        self.adjudication_reopened_from_complete = False
        self.adjudication_dirty = False

        self.adjudication_save_status.setText("Draft saved successfully.")
        self.adjudication_save_status.setToolTip(str(path))


    def resume_current_adjudication(self) -> None:
        """Load an existing draft for the selected reviewer and waveform."""
        started = perf_counter()

        try:
            self._resume_current_adjudication_impl()
        except Exception as exc:
            print("[ADJ-UI] Resume failed:", repr(exc))
            self.show_adjudication_error("Draft Resume Failed", str(exc))
        finally:
            self._adjudication_perf_log(
                "resume_current_adjudication",
                perf_counter() - started,
            )


    def _resume_current_adjudication_impl(self) -> None:
        """
        Restore a saved draft or completed adjudication.

        Completed sessions remain read-only until explicitly reopened.
        """
        if not self.confirm_discard_adjudication_changes():
            return

        record = self.adjudication_subject_dropdown.currentData()
        reviewer = self.adjudicator_dropdown.currentData()

        if not isinstance(record, dict) or not reviewer:
            raise ValueError("Select a record and adjudicator.")

        restored, navigation = load_existing_adjudication(
            record,
            str(reviewer),
        )

        # Existing waveform-loading path is reused for this selected record.
        self.adjudication_dirty = False
        self._load_adjudication_record_impl()

        self._clear_adjudication_selection_graphics()

        self.adjudication_comparison = restored
        self.adjudication_complete = bool(navigation["complete"])
        self.adjudication_reopened_from_complete = False

        self.draw_adjudication_timelines()
        self.populate_adjudication_table()

        index = navigation.get("selected_interval_index")

        if not isinstance(index, int) or not (
            0 <= index < len(restored.prefilled_intervals)
        ):
            index = 0

        if restored.prefilled_intervals:
            self.select_adjudication_interval(index)

        region_id = navigation.get("selected_region_id")

        for region in restored.comparison_regions:
            if region.region_id == region_id:
                self.adjudication_selected_region_id = region_id
                self._show_adjudication_region_details(region)
                self._highlight_adjudication_range(
                    region.start,
                    region.end,
                )
                break

        self.adjudication_dirty = False

        if self.adjudication_complete:
            self.apply_adjudication_read_only_state()
            self.adjudication_status_label.setText(
                "Completed adjudication loaded read-only. "
                "Use Reopen for Editing to revise it."
            )
            self.adjudication_save_status.setText(
                "Completed adjudication loaded."
            )
        else:
            self.adjudication_save_btn.setEnabled(True)
            self.adjudication_finalize_btn.setEnabled(True)
            self.adjudication_reopen_btn.setEnabled(False)
            self.adjudication_status_label.setText(
                "Draft restored, including labels and resolution state."
            )
            self.adjudication_save_status.setText("Saved draft loaded.")

        self.update_adjudication_navigation_controls()


    # =========================================================================
    # Reopening completed adjudications
    # =========================================================================

    def reopen_current_adjudication(self) -> None:
        """
        Explicitly reopen a completed adjudication with timing and error handling.

        This action changes in-memory state only. Completed output remains on disk
        until the first reopened draft save succeeds.
        """
        started = perf_counter()

        try:
            self._reopen_current_adjudication_impl()
        except Exception as exc:
            print("[ADJ-UI] Reopen failed:", repr(exc))
            self.show_adjudication_error(
                "Cannot Reopen Adjudication",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "reopen_current_adjudication",
                perf_counter() - started,
            )


    def _reopen_current_adjudication_impl(self) -> None:
        """Return a completed session to editable draft state."""
        comparison = self.adjudication_comparison

        if comparison is None or not self.adjudication_complete:
            raise ValueError("Load a completed adjudication first.")

        # Preserve previous terminal metadata on disk, but clear it in the draft.
        for interval in comparison.prefilled_intervals:
            interval.waveform_complete = False
            interval.terminal_event_status = ""
            interval.terminal_event_comment = ""

        self.adjudication_complete = False
        self.adjudication_reopened_from_complete = True
        self.adjudication_dirty = True

        self.draw_adjudication_boundary_handles()
        self.update_adjudication_label_controls()
        self.update_adjudication_boundary_controls()
        self.update_adjudication_navigation_controls()

        self.adjudication_save_btn.setEnabled(True)
        self.adjudication_finalize_btn.setEnabled(True)
        self.adjudication_reopen_btn.setEnabled(False)

        self.adjudication_status_label.setText(
            "Adjudication reopened for editing. Existing completed files "
            "remain preserved until the first successful draft save."
        )
        self.adjudication_save_status.setText(
            "Reopened session has not been saved."
        )


    # =========================================================================
    # Error Handling
    # =========================================================================

    def show_adjudication_error(
        self,
        title: str,
        message: str,
    ) -> None:
        """
        Show an error dialog with explicit, readable foreground/background colors.

        This styling applies only to the error dialog.
        """
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle(title)
        dialog.setText(str(message))
        dialog.setStandardButtons(QMessageBox.Ok)
        dialog.setStyleSheet(
            """
            QMessageBox {
                background-color: #FFFFFF;
            }
            QMessageBox QLabel {
                color: #00274C;
                background-color: #FFFFFF;
            }
            QMessageBox QPushButton {
                background-color: #00274C;
                color: #FFCB05;
                padding: 6px 12px;
            }
            """
        )
        dialog.exec_()