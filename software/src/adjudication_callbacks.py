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
import pandas as pd
import pyqtgraph as pg
from copy import deepcopy

from PyQt5.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PyQt5.QtCore import Qt, pyqtSignal

from processing import (
    get_events_for_window,
    list_subjects,
    load_waveforms_for_subject,
)
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
import json
from adjudication.config import ANNOTATION_USERS
from adjudication.discovery import build_source_annotation_filenames
from adjudication.paths import get_adjudication_paths

UM_MAIZE: str = "#FFCB05"
UM_BLUE: str = "#00274C"
UM_ACCENT: str = "#285680"
UM_RED: str = "#B71234"

ADJUDICATION_UI_PERF_ENABLED: bool = True

ADJUDICATION_WAVEFORM_ORDER: list[str] = [
    "I",
    "ABP",
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

# =============================================================================
# Encounter event marker configuration
# =============================================================================

ADJUDICATION_EVENT_COLOR: tuple[int, int, int] = (0, 128, 0)
ADJUDICATION_EVENT_LINE_WIDTH: float = 2.0
ADJUDICATION_EVENT_LABEL_FONT_SIZE: int = 8
ADJUDICATION_EVENT_LABEL_HEIGHT_FRACTION: float = 0.65

# =============================================================================
# Final boundary appearance
# =============================================================================

ADJUDICATION_BOUNDARY_COLOR = "#00274C"
ADJUDICATION_BOUNDARY_WIDTH = 2.0

ADJUDICATION_BOUNDARY_HOVER_COLOR = "#285680"
ADJUDICATION_BOUNDARY_HOVER_WIDTH = 5.0

ADJUDICATION_BOUNDARY_SELECTED_COLOR = "#D50032"
ADJUDICATION_BOUNDARY_SELECTED_WIDTH = 6.0

# Selected interval/review-region outline.
ADJUDICATION_SELECTION_COLOR = "#FFCB05"
ADJUDICATION_SELECTION_LINE_WIDTH = 4.0
ADJUDICATION_SELECTION_FILL_ALPHA = 5

# Boundaries of the colored timeline blocks.
ADJUDICATION_TIMELINE_EDGE_COLOR = "#D49A00"
ADJUDICATION_TIMELINE_EDGE_WIDTH = 2.5

# Temporary guide showing a final boundary's position while dragging.
ADJUDICATION_DRAG_GUIDE_COLOR = "#00274C"
ADJUDICATION_DRAG_GUIDE_WIDTH = 2.5

# =============================================================================
# Automatic Y scaling
# =============================================================================

ADJUDICATION_AUTO_Y_MAX_WINDOW_SEC: float = 300.0
ADJUDICATION_AUTO_Y_DEBOUNCE_MS: int = 200
ADJUDICATION_AUTO_Y_BUFFER_SEC: float = 2.0
ADJUDICATION_AUTO_Y_MARGIN_FRACTION: float = 0.10
ADJUDICATION_AUTO_Y_MIN_SPAN: float = 0.25


# Save changed adjudication drafts every two minutes.
ADJUDICATION_AUTOSAVE_INTERVAL_MS: int = 2 * 60 * 1000

class SelectableAdjudicationBoundary(pg.InfiniteLine):
    """
    Draggable final boundary that also supports explicit left-click selection.

    Accepting the click prevents the timeline's scene handler from treating
    the same click as an ordinary interval selection.
    """

    boundarySelected = pyqtSignal(object)

    def hoverEvent(self, event: Any) -> None:
        """Reserve left clicks near the boundary while retaining drag behavior."""
        super().hoverEvent(event)

        if not event.isExit():
            event.acceptClicks(Qt.LeftButton)

    def mouseClickEvent(self, event: Any) -> None:
        """Select this boundary on a left click."""
        if event.button() == Qt.LeftButton:
            event.accept()
            self.boundarySelected.emit(self)
            return

        super().mouseClickEvent(event)

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
        # Selecting Set Folder is an explicit refresh of this batch.
        self.adjudication_record_status_cache.clear()
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

        self.refresh_adjudication_record_statuses(force=True)


    # =========================================================================
    # Record readiness and adjudication status
    # =========================================================================

    def _adjudication_record_key(
        self,
        record: dict[str, Any],
    ) -> str:
        """
        Return the known output path as a stable waveform-record key.

        Avoid resolving network paths during dropdown updates.
        """
        return str(record.get("output_path", "")).rstrip("/\\")


    def inspect_adjudication_record_status(
        self,
        record: dict[str, Any],
        reviewer: str,
    ) -> dict[str, str]:
        """
        Inspect input readiness and saved state for one waveform record.

        Checks only expected files under known output paths. This does not
        rediscover waveform files, read source CSV contents, or hash saved files.

        Full validation still occurs when loading or resuming.
        """
        output_value = record.get("output_path")

        if not output_value:
            return {
                "status": "Check Files",
                "details": "The record has no output_path.",
            }

        output = Path(str(output_value))
        missing_users: list[str] = []

        try:
            # Check the exact source filenames required by the file contract.
            for username in ANNOTATION_USERS:
                _, complete_name = build_source_annotation_filenames(
                    subject=record["subject"],
                    file_tag=record["file_tag"],
                    username=username,
                )

                if not (output / username / complete_name).is_file():
                    missing_users.append(username)

            input_detail = (
                "Completed inputs available."
                if not missing_users
                else "Missing completed input(s): " + ", ".join(missing_users)
            )

            if not reviewer:
                return {
                    "status": "Not Ready" if missing_users else "Ready",
                    "details": input_detail + " Select an adjudicator.",
                }

            paths = get_adjudication_paths(
                record_output_path=output,
                subject=record["subject"],
                file_tag=record["file_tag"],
                adjudicator=reviewer,
            )

            draft_exists = paths.draft_csv.is_file()
            complete_exists = paths.complete_csv.is_file()
            state_exists = paths.state_json.is_file()

            if state_exists:
                state = json.loads(
                    paths.state_json.read_text(encoding="utf-8")
                )

                # The state identifies the active CSV, even if an old completed
                # file remains after a cleanup failure.
                status = state.get("status")

                identity_matches = (
                    str(state.get("adjudicator", "")) == reviewer
                    and str(state.get("subject", "")) == str(record["subject"])
                    and str(state.get("encounter", "")) == str(record["encounter"])
                    and str(state.get("file_tag", "")) == str(record["file_tag"])
                )

                if not identity_matches:
                    return {
                        "status": "Check Files",
                        "details": "Saved state identity does not match this record.",
                    }

                if status == "draft" and draft_exists:
                    return {
                        "status": "Draft",
                        "details": "Saved draft available. " + input_detail,
                    }

                if status == "complete" and complete_exists:
                    return {
                        "status": "Complete",
                        "details": "Completed adjudication available. " + input_detail,
                    }

                return {
                    "status": "Check Files",
                    "details": (
                        "State JSON references a missing CSV or unsupported status."
                    ),
                }

            if draft_exists or complete_exists:
                return {
                    "status": "Check Files",
                    "details": "An adjudication CSV exists without its state JSON.",
                }

            return {
                "status": "Not Ready" if missing_users else "Ready",
                "details": input_detail,
            }

        except Exception as exc:
            print(
                "[ADJ-UI] Record status inspection failed:",
                type(exc).__name__,
                exc,
            )
            return {
                "status": "Check Files",
                "details": f"Status could not be checked: {exc}",
            }


    def _apply_adjudication_record_status(
        self,
        index: int,
        record: dict[str, Any],
        status: dict[str, str],
    ) -> None:
        """
        Update one dropdown item's text and tooltip without changing its data.
        """
        name = str(record.get("name", "Waveform record"))

        self.adjudication_subject_dropdown.setItemText(
            index,
            f"[{status['status']}] {name}",
        )
        self.adjudication_subject_dropdown.setItemData(
            index,
            status["details"],
            Qt.ToolTipRole,
        )


    def refresh_adjudication_record_statuses(
        self,
        force: bool = False,
    ) -> None:
        """
        Refresh dropdown statuses for the currently selected adjudicator.

        Existing cached values are reused unless force=True. Reviewer changes
        do not reload waveforms or discard an active reviewer session.
        """
        started = perf_counter()

        try:
            self._refresh_adjudication_record_statuses_impl(force)
        except Exception as exc:
            print("[ADJ-UI] Status refresh failed:", repr(exc))
            self.show_adjudication_error(
                "Status Refresh Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "refresh_adjudication_record_statuses",
                perf_counter() - started,
            )


    def _refresh_adjudication_record_statuses_impl(
        self,
        force: bool,
    ) -> None:
        """
        Check known records and update labels without rebuilding the dropdown.
        """
        reviewer = str(self.adjudicator_dropdown.currentData() or "")
        dropdown = self.adjudication_subject_dropdown

        for index in range(dropdown.count()):
            record = dropdown.itemData(index)

            if not isinstance(record, dict):
                continue

            cache_key = (
                self._adjudication_record_key(record),
                reviewer,
            )

            if force or cache_key not in self.adjudication_record_status_cache:
                self.adjudication_record_status_cache[cache_key] = (
                    self.inspect_adjudication_record_status(
                        record,
                        reviewer,
                    )
                )

            self._apply_adjudication_record_status(
                index,
                record,
                self.adjudication_record_status_cache[cache_key],
            )

        self.update_adjudication_load_availability()


    def handle_adjudication_reviewer_changed(
        self,
        *args: Any,
    ) -> None:
        """
        Display statuses for the selected reviewer.

        The currently loaded session retains its original reviewer identity;
        saving continues to use adjudication_loaded_record and comparison data.
        """
        self.refresh_adjudication_record_statuses()


    def refresh_loaded_adjudication_record_status(
        self,
        status_override: Optional[str] = None,
    ) -> None:
        """
        Update only the loaded waveform's status after a workflow action.

        Parameters
        ----------
        status_override : str or None
            Use an in-memory status without filesystem checks. For example,
            reopening a completed session shows Draft although its previous
            completed files remain on disk until the first successful draft save.
        """
        started = perf_counter()

        try:
            self._refresh_loaded_adjudication_record_status_impl(
                status_override
            )
        finally:
            self._adjudication_perf_log(
                "refresh_loaded_adjudication_record_status",
                perf_counter() - started,
            )


    def _refresh_loaded_adjudication_record_status_impl(
        self,
        status_override: Optional[str],
    ) -> None:
        """Refresh the loaded record without scanning other records."""
        record = getattr(self, "adjudication_loaded_record", None)
        comparison = self.adjudication_comparison

        if not isinstance(record, dict) or comparison is None:
            return

        reviewer = comparison.adjudicator
        record_key = self._adjudication_record_key(record)

        if status_override is not None:
            status = {
                "status": status_override,
                "details": (
                    "Unsaved editable session. Existing completed output "
                    "is preserved until a draft is saved."
                ),
            }
        else:
            status = self.inspect_adjudication_record_status(
                record,
                reviewer,
            )

        self.adjudication_record_status_cache[
            (record_key, reviewer)
        ] = status

        # Do not show one reviewer's state under another reviewer selection.
        selected_reviewer = str(
            self.adjudicator_dropdown.currentData() or ""
        )

        if selected_reviewer != reviewer:
            return

        dropdown = self.adjudication_subject_dropdown

        for index in range(dropdown.count()):
            item_record = dropdown.itemData(index)

            if (
                isinstance(item_record, dict)
                and self._adjudication_record_key(item_record) == record_key
            ):
                self._apply_adjudication_record_status(
                    index,
                    item_record,
                    status,
                )
                break


    # =========================================================================
    # Encounter event loading and graphics
    # =========================================================================

    def load_adjudication_events(
        self,
        record: dict[str, Any],
    ) -> None:
        """
        Load encounter events using the existing manifest parser.

        Event loading is optional. A missing or invalid manifest must not prevent
        waveform viewing, comparison, or adjudication saving.

        Parameters
        ----------
        record : dict[str, Any]
            Selected waveform record containing manifest_path or encounter_path.

        Notes
        -----
        The shared parser interprets naive event times as America/New_York and
        returns absolute UTC epoch seconds.

        Events are retained even when outside the loaded waveform window.
        """
        started = perf_counter()

        try:
            self._load_adjudication_events_impl(record)
        except Exception as exc:
            self.adjudication_events = []
            self.adjudication_event_labels_btn.setEnabled(False)

            print(
                "[ADJ-UI] Optional event loading failed:",
                type(exc).__name__,
                exc,
            )

            self.show_adjudication_error(
                "Event Metadata Could Not Be Loaded",
                f"Waveform review can continue without event markers.\n\n{exc}",
            )
        finally:
            self._adjudication_perf_log(
                "load_adjudication_events",
                perf_counter() - started,
            )


    def _load_adjudication_events_impl(
        self,
        record: dict[str, Any],
    ) -> None:
        """
        Resolve the encounter manifest and normalize its event display records.
        """
        self.adjudication_events = []

        configured_path = record.get("manifest_path")

        if configured_path:
            manifest_path = Path(str(configured_path)).expanduser()
        else:
            encounter_path = record.get("encounter_path")

            if not encounter_path:
                print(
                    "[ADJ-UI] No encounter path available for event loading."
                )
                self.adjudication_event_labels_btn.setEnabled(False)
                return

            manifest_path = (
                Path(str(encounter_path)).expanduser()
                / "waveform_manifest.csv"
            )

        self.adjudication_manifest_path = str(manifest_path)

        if not manifest_path.is_file():
            print(
                "[ADJ-UI] Optional manifest not found:",
                manifest_path,
            )
            self.adjudication_event_labels_btn.setEnabled(False)
            return

        events = get_events_for_window(
            manifest_path=str(manifest_path),
            subject=str(record.get("subject", "")),
            encounter=str(record.get("encounter", "")),
            window_start=None,
            window_end=None,
        )

        required_columns = {
            "event_sec",
            "FLO_MEAS_NAME",
            "FLOWSHEET_VALUE",
        }

        if not required_columns.issubset(events.columns):
            raise ValueError(
                "The event parser did not return the required columns: "
                + ", ".join(sorted(required_columns))
            )

        for _, row in events.iterrows():
            try:
                event_time = float(row["event_sec"])
            except (TypeError, ValueError):
                continue

            if not np.isfinite(event_time):
                continue

            name_value = row["FLO_MEAS_NAME"]
            value_value = row["FLOWSHEET_VALUE"]

            event_name = (
                ""
                if pd.isna(name_value)
                else str(name_value).strip()
            )
            event_value = (
                ""
                if pd.isna(value_value)
                else str(value_value).strip()
            )

            self.adjudication_events.append(
                {
                    "time": event_time,
                    "name": event_name or "Clinical Event",
                    "value": event_value,
                }
            )

        self.adjudication_event_labels_btn.setEnabled(
            bool(self.adjudication_events)
        )

        print(
            "[ADJ-UI] Encounter events loaded:",
            len(self.adjudication_events),
            "| manifest:",
            manifest_path,
        )


    def clear_adjudication_event_graphics(
        self,
        plot: Optional[pg.PlotWidget] = None,
    ) -> None:
        """
        Remove event graphics from one waveform plot or all waveform plots.

        Waveform curves, annotation overlays, and selection highlights are retained.
        """
        retained: list[tuple[pg.PlotWidget, Any]] = []

        for owner_plot, item in self.adjudication_event_graphics:
            if plot is not None and owner_plot is not plot:
                retained.append((owner_plot, item))
                continue

            # Lead switching may already have removed the item with plot.clear().
            if item.scene() is not None:
                owner_plot.removeItem(item)

        self.adjudication_event_graphics = retained


    def draw_adjudication_events(
        self,
        row_index: Optional[int] = None,
    ) -> None:
        """
        Render encounter event lines and labels with timing diagnostics.

        Parameters
        ----------
        row_index : int or None
            One waveform row to refresh, or all waveform rows when omitted.
        """
        started = perf_counter()

        try:
            self._draw_adjudication_events_impl(row_index)
        except Exception as exc:
            print(
                "[ADJ-UI] Event rendering failed:",
                type(exc).__name__,
                exc,
            )
            raise
        finally:
            self._adjudication_perf_log(
                "draw_adjudication_events",
                perf_counter() - started,
            )


    def _draw_adjudication_events_impl(
        self,
        row_index: Optional[int],
    ) -> None:
        """
        Add event lines without expanding waveform or Auto-Y bounds.
        """
        if row_index is None:
            rows = range(len(self.adjudication_waveform_plots))
            self.clear_adjudication_event_graphics()
        else:
            if not 0 <= row_index < len(self.adjudication_waveform_plots):
                raise ValueError("Invalid event-rendering waveform row.")

            rows = [row_index]
            self.clear_adjudication_event_graphics(
                self.adjudication_waveform_plots[row_index]
            )

        event_pen = pg.mkPen(
            ADJUDICATION_EVENT_COLOR,
            width=ADJUDICATION_EVENT_LINE_WIDTH,
            style=Qt.DashLine,
        )

        for row in rows:
            plot = self.adjudication_waveform_plots[row]

            if self.adjudication_lead_selectors[row].currentData() is None:
                continue

            for event in self.adjudication_events:
                event_time = float(event["time"])
                event_name = str(event["name"])
                event_value = str(event["value"])

                utc_time = pd.to_datetime(
                    event_time,
                    unit="s",
                    utc=True,
                )
                eastern_time = utc_time.tz_convert("America/New_York")

                tooltip = (
                    f"{event_name}\n"
                    f"Value: {event_value or 'None'}\n"
                    f"UTC: {utc_time.isoformat()}\n"
                    f"Eastern: {eastern_time.isoformat()}"
                )

                line = pg.InfiniteLine(
                    pos=event_time,
                    angle=90,
                    movable=False,
                    pen=event_pen,
                )
                line.setZValue(100)
                line.setToolTip(tooltip)

                plot.addItem(line, ignoreBounds=True)
                self.adjudication_event_graphics.append((plot, line))

                label = pg.TextItem(
                    text=event_name,
                    color=ADJUDICATION_EVENT_COLOR,
                    anchor=(0, 0.5),
                    fill=pg.mkBrush(255, 255, 255, 215),
                    border=pg.mkPen(ADJUDICATION_EVENT_COLOR),
                )

                font = label.textItem.font()
                font.setPointSize(ADJUDICATION_EVENT_LABEL_FONT_SIZE)
                label.setFont(font)

                label.setZValue(200)
                label.setToolTip(tooltip)
                label.setVisible(self.adjudication_event_labels_visible)

                # Keep the timestamp available for repositioning after Y changes.
                label.adjudication_event_time = event_time

                plot.addItem(label, ignoreBounds=True)
                self.adjudication_event_graphics.append((plot, label))

            self.update_adjudication_event_label_positions(row)


    def update_adjudication_event_label_positions(
        self,
        row_index: int,
    ) -> None:
        """
        Keep event labels inside the plot after Y-axis changes.

        Positions change only in Y; the event's absolute epoch X coordinate stays
        fixed. This does not rebuild graphics or reread the manifest.
        """
        plot = self.adjudication_waveform_plots[row_index]
        y_min, y_max = plot.viewRange()[1]

        if (
            not np.isfinite(y_min)
            or not np.isfinite(y_max)
            or y_max <= y_min
        ):
            return

        label_y = (
            y_min
            + (y_max - y_min)
            * ADJUDICATION_EVENT_LABEL_HEIGHT_FRACTION
        )

        for owner_plot, item in self.adjudication_event_graphics:
            if owner_plot is plot and isinstance(item, pg.TextItem):
                item.setPos(
                    float(item.adjudication_event_time),
                    float(label_y),
                )


    def toggle_adjudication_event_labels(self) -> None:
        """
        Toggle event text visibility while retaining vertical event lines.
        """
        started = perf_counter()

        try:
            self._toggle_adjudication_event_labels_impl()
        finally:
            self._adjudication_perf_log(
                "toggle_adjudication_event_labels",
                perf_counter() - started,
            )


    def _toggle_adjudication_event_labels_impl(self) -> None:
        """Change existing label visibility without rebuilding event graphics."""
        self.adjudication_event_labels_visible = (
            not self.adjudication_event_labels_visible
        )

        for _, item in self.adjudication_event_graphics:
            if isinstance(item, pg.TextItem):
                item.setVisible(
                    self.adjudication_event_labels_visible
                )

        self.adjudication_event_labels_btn.setText(
            "Hide Event Labels"
            if self.adjudication_event_labels_visible
            else "Show Event Labels"
        )


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

        # Events remain available even if source annotation comparison later fails.
        self.load_adjudication_events(record)
        self.draw_adjudication_events()

        # Calipers are available even if annotation comparison cannot be loaded.
        self.adjudication_calipers.refresh_sources()

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

        self.adjudication_selected_boundary_index = None

        self.clear_adjudication_boundary_drag_guides()

        # Stop pending scaling before clearing the old waveform arrays and plots.
        self.adjudication_auto_y_timer.stop()

        # Each newly loaded record starts with automatic scaling requested.
        self.adjudication_auto_y_enabled = [
            True
            for _ in self.adjudication_waveform_plots
        ]

        self.adjudication_calipers.clear()
        self.adjudication_calipers.toggle_button.setEnabled(False)
        self.adjudication_calipers.source_dropdown.setEnabled(False)

        self.clear_adjudication_waveform_overlays()

        self.clear_adjudication_event_graphics()
        self.adjudication_events = []
        self.adjudication_event_labels_btn.setEnabled(False)

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

        loaded_record = getattr(self, "adjudication_loaded_record", None)
        loaded_comparison = self.adjudication_comparison

        if isinstance(loaded_record, dict) and loaded_comparison is not None:
            cache_key = (
                self._adjudication_record_key(loaded_record),
                loaded_comparison.adjudicator,
            )

            # Discard cached in-memory overrides. The next check reflects disk state.
            self.adjudication_record_status_cache.pop(cache_key, None)

        self.adjudication_loaded_record = None
        self.adjudication_loaded_reviewer = ""

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
        """
        Populate waveform selectors and initially display ABP in the second row.

        Only loaded signals with usable data are supplied in available_indices.
        All available signals remain selectable in every row.
        """
        display_order = list(available_indices)

        abp_index = next(
            (
                index
                for index in display_order
                if str(
                    self.adjudication_lead_names[index]
                ).strip().upper() == "ABP"
            ),
            None,
        )

        if abp_index is not None:
            display_order.remove(abp_index)

            # Keep the first available non-ABP signal first, followed by ABP.
            display_order.insert(
                min(1, len(display_order)),
                abp_index,
            )

        for row_index, selector in enumerate(
            self.adjudication_lead_selectors
        ):
            blocked = selector.blockSignals(True)

            try:
                selector.clear()

                for signal_index in available_indices:
                    selector.addItem(
                        str(self.adjudication_lead_names[signal_index]),
                        signal_index,
                    )

                if display_order:
                    initial_signal_index = display_order[
                        min(row_index, len(display_order) - 1)
                    ]

                    selector.setCurrentIndex(
                        selector.findData(initial_signal_index)
                    )

                selector.setEnabled(bool(available_indices))
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

        # Fit a newly displayed signal once without changing the row's Auto-Y
        # preference. Its button then reflects ON, OFF, or PAUSED.
        self.autoscale_adjudication_row(
            row_index,
            respect_window_limit=False,
        )

        for button in self.adjudication_y_controls[row_index].values():
            button.setEnabled(True)

        self.update_adjudication_auto_y_buttons()

        # plot.clear() removed this row's overlays; recreate them for the new lead.
        self.draw_adjudication_waveform_overlays(row_index)
        self.draw_adjudication_events(row_index)
        # Lead changes clear plot items, so restore the retained caliper positions.
        self.adjudication_calipers.redraw()


    def adjust_adjudication_y(
        self,
        row_index: int,
        action: str,
    ) -> None:
        """
        Apply manual Y adjustment or explicitly fit the visible signal.

        Manual zooming/shifting disables Auto-Y for that row.
        The 'auto' action fits the current window without changing preference.
        """
        started = perf_counter()

        try:
            self._adjust_adjudication_y_impl(row_index, action)
        except Exception as exc:
            print("[ADJ-UI] Y adjustment failed:", repr(exc))
            self.show_adjudication_error(
                "Y Adjustment Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "adjust_adjudication_y",
                perf_counter() - started,
            )


    def _adjust_adjudication_y_impl(
        self,
        row_index: int,
        action: str,
    ) -> None:
        """Adjust one row without modifying waveform data."""
        if action == "auto":
            self.autoscale_adjudication_row(
                row_index,
                respect_window_limit=False,
            )
            self.update_adjudication_auto_y_buttons()
            return

        if action not in {"in", "out", "up", "down"}:
            raise ValueError(f"Unsupported Y adjustment: {action!r}")

        self.adjudication_auto_y_enabled[row_index] = False

        plot = self.adjudication_waveform_plots[row_index]
        low, high = plot.viewRange()[1]

        center = (low + high) / 2.0
        span = max(high - low, ADJUDICATION_AUTO_Y_MIN_SPAN)

        if action == "in":
            span *= 0.8
        elif action == "out":
            span *= 1.25
        elif action == "up":
            center += span * 0.2
        elif action == "down":
            center -= span * 0.2

        plot.setYRange(
            center - span / 2.0,
            center + span / 2.0,
            padding=0,
        )

        self.update_adjudication_auto_y_buttons()


    # =========================================================================
    # Automatic Y scaling
    # =========================================================================

    def update_adjudication_auto_y_buttons(self) -> None:
        """
        Display each row's Auto-Y preference and window-limit status.

        Paused means Auto-Y is requested but the visible window is too large.
        """
        if not self.adjudication_waveform_plots:
            return

        x_min, x_max = (
            self.adjudication_waveform_plots[0].viewRange()[0]
        )
        paused = (
            float(x_max - x_min)
            > ADJUDICATION_AUTO_Y_MAX_WINDOW_SEC
        )

        for row_index, controls in enumerate(self.adjudication_y_controls):
            button = controls["AUTO-Y"]
            available = (
                self.adjudication_lead_selectors[row_index].currentData()
                is not None
            )
            button.setEnabled(available)

            if not self.adjudication_auto_y_enabled[row_index]:
                button.setText("AUTO OFF")
                button.setToolTip(
                    "Manual Y scaling. Click to enable automatic scaling."
                )
            elif paused:
                button.setText("PAUSED")
                button.setToolTip(
                    "Auto-Y resumes when the visible window is "
                    f"{ADJUDICATION_AUTO_Y_MAX_WINDOW_SEC:g} seconds or less."
                )
            else:
                button.setText("AUTO ON")
                button.setToolTip(
                    "Automatically fit this signal after horizontal navigation. "
                    "Click to turn off."
                )


    def toggle_adjudication_auto_y(self, row_index: int) -> None:
        """Toggle a row's automatic scaling preference with timing."""
        started = perf_counter()

        try:
            self._toggle_adjudication_auto_y_impl(row_index)
        finally:
            self._adjudication_perf_log(
                "toggle_adjudication_auto_y",
                perf_counter() - started,
            )


    def _toggle_adjudication_auto_y_impl(self, row_index: int) -> None:
        """Enable or disable Auto-Y without changing other rows."""
        self.adjudication_auto_y_enabled[row_index] = (
            not self.adjudication_auto_y_enabled[row_index]
        )

        if self.adjudication_auto_y_enabled[row_index]:
            self.autoscale_adjudication_row(row_index)

        self.update_adjudication_auto_y_buttons()


    def schedule_adjudication_auto_y(self, *args: Any) -> None:
        """
        Restart the debounce timer after the shared X-range changes.

        Repeated navigation postpones calculation until movement pauses.
        """
        self.update_adjudication_auto_y_buttons()

        if any(self.adjudication_auto_y_enabled):
            self.adjudication_auto_y_timer.start(
                ADJUDICATION_AUTO_Y_DEBOUNCE_MS
            )


    def autoscale_adjudication_visible_rows(self) -> None:
        """Fit enabled rows after navigation, with timing diagnostics."""
        started = perf_counter()

        try:
            self._autoscale_adjudication_visible_rows_impl()
        except Exception as exc:
            # Avoid repeated modal dialogs during navigation.
            print("[ADJ-UI] Automatic Y scaling failed:", repr(exc))
        finally:
            self._adjudication_perf_log(
                "autoscale_adjudication_visible_rows",
                perf_counter() - started,
            )


    def _autoscale_adjudication_visible_rows_impl(self) -> None:
        """Scale enabled rows only when the shared window is sufficiently small."""
        for row_index, enabled in enumerate(
            self.adjudication_auto_y_enabled
        ):
            if enabled:
                self.autoscale_adjudication_row(row_index)

        self.update_adjudication_auto_y_buttons()


    def autoscale_adjudication_row(
        self,
        row_index: int,
        *,
        respect_window_limit: bool = True,
    ) -> bool:
        """
        Fit a row to finite samples in the visible window plus a small buffer.

        Returns
        -------
        bool
            True when a valid Y range was applied.

        Notes
        -----
        This uses the row's selected source time axis. It does not interpolate,
        reread files, or change stored signal values.
        """
        signal_index = (
            self.adjudication_lead_selectors[row_index].currentData()
        )

        if signal_index is None:
            return False

        plot = self.adjudication_waveform_plots[row_index]
        x_min, x_max = plot.viewRange()[0]
        x_min, x_max = float(x_min), float(x_max)

        if (
            not np.isfinite(x_min)
            or not np.isfinite(x_max)
            or x_max <= x_min
        ):
            return False

        if (
            respect_window_limit
            and x_max - x_min > ADJUDICATION_AUTO_Y_MAX_WINDOW_SEC
        ):
            return False

        times, values = self._adjudication_signal_arrays(
            int(signal_index)
        )

        if times.size < 2:
            return False

        # First select the time window, then inspect only its signal values.
        # A mask also supports per-lead axes containing non-finite timestamps.
        in_window = (
            np.isfinite(times)
            & (times >= x_min - ADJUDICATION_AUTO_Y_BUFFER_SEC)
            & (times <= x_max + ADJUDICATION_AUTO_Y_BUFFER_SEC)
        )

        segment = values[in_window]
        segment = segment[np.isfinite(segment)]

        if segment.size < 2:
            return False

        low, high = np.percentile(segment, [0.5, 99.5])

        if not np.isfinite(low) or not np.isfinite(high):
            return False

        center = float((low + high) / 2.0)
        span = max(
            float(high - low),
            ADJUDICATION_AUTO_Y_MIN_SPAN,
        )
        half_span = span * (
            0.5 + ADJUDICATION_AUTO_Y_MARGIN_FRACTION
        )

        plot.setYRange(
            center - half_span,
            center + half_span,
            padding=0,
        )

        return True

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
        """
        Draw a read-only timeline block with explicit, visible boundary lines.

        These block edges are separate from the selectable final boundary handles.
        """
        region = pg.LinearRegionItem(
            values=[float(start), float(end)],
            movable=False,
            brush=pg.mkBrush(*color),
            pen=pg.mkPen(
                ADJUDICATION_TIMELINE_EDGE_COLOR,
                width=ADJUDICATION_TIMELINE_EDGE_WIDTH,
            ),
        )

        plot.addItem(region, ignoreBounds=True)

        text = pg.TextItem(
            str(label),
            color="#00274C",
            anchor=(0.5, 0.5),
        )
        text.setPos(
            float(start) + (float(end) - float(start)) / 2.0,
            0.5,
        )

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
        Highlight the selected interval or review region with a distinct outline.

        These yellow lines indicate selection only. They are not draggable
        adjudication boundaries or caliper markers.
        """
        self._clear_adjudication_selection_graphics()

        plots = self.adjudication_waveform_plots + [
            self.adjudication_timeline_plots["Final Adjudication"]
        ]

        for plot in plots:
            highlight = pg.LinearRegionItem(
                values=[float(start), float(end)],
                movable=False,
                brush=pg.mkBrush(
                    255,
                    203,
                    5,
                    ADJUDICATION_SELECTION_FILL_ALPHA,
                ),
                pen=pg.mkPen(
                    ADJUDICATION_SELECTION_COLOR,
                    width=ADJUDICATION_SELECTION_LINE_WIDTH,
                ),
            )

            # Above interval shading, but below selectable boundary handles.
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
        self.clear_adjudication_boundary_selection()

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
        # A selectable boundary already handled this click.
        if mouse_event.isAccepted():
            return

        if mouse_event.button() != Qt.LeftButton:
            return

        if getattr(self, "adjudication_caliper_adjust_active", False):
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
        self.refresh_loaded_adjudication_record_status()


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
        Enable insertion by interval selection and removal by boundary selection.
        """
        self.adjudication_remove_boundary_btn.setText(
            "Remove Selected Boundary"
        )

        if (
            getattr(self, "adjudication_complete", False)
            or getattr(self, "adjudication_caliper_adjust_active", False)
        ):
            self.adjudication_add_boundary_btn.setEnabled(False)
            self.adjudication_remove_boundary_btn.setEnabled(False)
            return

        if self.adjudication_pending_split_index is not None:
            self.adjudication_add_boundary_btn.setEnabled(True)
            self.adjudication_add_boundary_btn.setText("Cancel Add")
            self.adjudication_remove_boundary_btn.setEnabled(False)
            return

        self.adjudication_add_boundary_btn.setText("Add Boundary")

        comparison = self.adjudication_comparison
        interval_index = self.adjudication_selected_interval_index
        boundary_index = self.adjudication_selected_boundary_index

        has_interval = (
            comparison is not None
            and interval_index is not None
            and 0 <= interval_index < len(comparison.prefilled_intervals)
        )

        can_add = (
            has_interval
            and comparison.prefilled_intervals[interval_index].duration
            >= 2.0 * MINIMUM_VALID_INTERVAL_SEC
        )

        can_remove = (
            comparison is not None
            and boundary_index is not None
            and 0 <= boundary_index < len(comparison.prefilled_intervals) - 1
        )

        self.adjudication_add_boundary_btn.setEnabled(can_add)
        self.adjudication_remove_boundary_btn.setEnabled(can_remove)

        self.adjudication_remove_boundary_btn.setToolTip(
            "Click an internal final-timeline boundary first. "
            "Only that selected boundary will be removed."
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
        if getattr(self, "adjudication_caliper_adjust_active", False):
            raise ValueError(
                "Turn caliper Adjust off before adding an adjudication boundary."
            )

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
        Route manual caliper dots before final-boundary placement.

        Temporary caliper interactions never modify final adjudication data.
        """
        if mouse_event.button() != Qt.LeftButton:
            return

        # Manual labeling consumes the click before the shared editing guard.
        if self.adjudication_calipers.handle_waveform_click(
            row_index,
            mouse_event,
        ):
            return

        # Both marker adjustment and manual labeling suppress adjudication clicks.
        if getattr(self, "adjudication_caliper_adjust_active", False):
            return

        if self.adjudication_pending_split_index is None:
            return

        plot = self.adjudication_waveform_plots[row_index]
        view_box = plot.getViewBox()

        if not view_box.sceneBoundingRect().contains(mouse_event.scenePos()):
            return

        point = view_box.mapSceneToView(mouse_event.scenePos())
        self.place_adjudication_boundary(float(point.x()))


    def _remove_adjudication_boundary_impl(self) -> None:
        """
        Remove exactly the selected internal boundary.

        Identical neighboring labels are retained. Different labels or comments
        require confirmation and produce an unlabeled merged interval.
        """
        comparison = self.adjudication_comparison
        index = self.adjudication_selected_boundary_index

        if self.adjudication_complete:
            raise ValueError("Reopen the completed adjudication before editing.")

        if self.adjudication_caliper_adjust_active:
            raise ValueError("Turn caliper interaction modes off first.")

        if self.adjudication_pending_split_index is not None:
            raise ValueError("Finish or cancel Add Boundary first.")

        if comparison is None or index is None:
            raise ValueError("Click the boundary you want to remove first.")

        intervals = comparison.prefilled_intervals

        if not 0 <= index < len(intervals) - 1:
            raise ValueError("The selected internal boundary is unavailable.")

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Apply pending label changes before removing a boundary."
            )

        left = intervals[index]
        right = intervals[index + 1]

        if abs(left.end - right.start) > 1e-6:
            raise ValueError("The boundary's neighboring intervals are not contiguous.")

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
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Remove Selected Boundary")
            dialog.setIcon(QMessageBox.Question)
            dialog.setText(
                "The intervals on either side have different labels or comments."
            )
            dialog.setInformativeText(
                "Removing this boundary will merge those two intervals and clear "
                "their final CPR, rhythm, and explanation."
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

        # Interval indices changed; discard the old boundary selection.
        self.adjudication_selected_boundary_index = None
        self.adjudication_dirty = True

        self.refresh_adjudication_after_structure_change(index)

        self.adjudication_status_label.setText(
            "Selected boundary removed. Its neighboring intervals were merged."
            if labels_match
            else "Selected boundary removed. Assign a label to the merged interval."
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
        """
        Draw selectable internal final boundaries with minimum-duration limits.

        Dragging must preserve at least MINIMUM_VALID_INTERVAL_SEC in each
        neighboring interval. Limits use the neighbors' outer endpoints so
        movement remains reversible.

        Existing invalid short fragments remain selectable for removal, but
        cannot be dragged until their interval structure is corrected.
        """
        plot = self.adjudication_timeline_plots["Final Adjudication"]

        for line in getattr(self, "adjudication_boundary_lines", []):
            if line.scene() is not None:
                plot.removeItem(line)

        self.adjudication_boundary_lines = []

        comparison = self.adjudication_comparison

        if comparison is None:
            return

        intervals = comparison.prefilled_intervals

        editing_available = (
            not getattr(self, "adjudication_complete", False)
            and not getattr(self, "adjudication_caliper_adjust_active", False)
            and self.adjudication_pending_split_index is None
        )

        minimum_duration = float(MINIMUM_VALID_INTERVAL_SEC)

        if not np.isfinite(minimum_duration) or minimum_duration <= 0:
            raise ValueError(
                "MINIMUM_VALID_INTERVAL_SEC must be finite and positive."
            )

        for left_index in range(len(intervals) - 1):
            left = intervals[left_index]
            right = intervals[left_index + 1]

            current_boundary = float(left.end)

            # Fixed outer endpoints prevent the previous one-way drag restriction.
            lower_bound = float(left.start + minimum_duration)
            upper_bound = float(right.end - minimum_duration)

            valid_drag_range = (
                np.isfinite(current_boundary)
                and np.isfinite(lower_bound)
                and np.isfinite(upper_bound)
                and lower_bound < upper_bound
                and lower_bound <= current_boundary <= upper_bound
            )

            selected = (
                left_index == self.adjudication_selected_boundary_index
            )

            line = SelectableAdjudicationBoundary(
                pos=current_boundary,
                angle=90,
                movable=editing_available and valid_drag_range,
                bounds=(
                    [lower_bound, upper_bound]
                    if valid_drag_range
                    else [current_boundary, current_boundary]
                ),
                pen=pg.mkPen(
                    ADJUDICATION_BOUNDARY_SELECTED_COLOR
                    if selected
                    else ADJUDICATION_BOUNDARY_COLOR,
                    width=(
                        ADJUDICATION_BOUNDARY_SELECTED_WIDTH
                        if selected
                        else ADJUDICATION_BOUNDARY_WIDTH
                    ),
                ),
                hoverPen=pg.mkPen(
                    ADJUDICATION_BOUNDARY_SELECTED_COLOR
                    if selected
                    else ADJUDICATION_BOUNDARY_HOVER_COLOR,
                    width=(
                        ADJUDICATION_BOUNDARY_SELECTED_WIDTH
                        if selected
                        else ADJUDICATION_BOUNDARY_HOVER_WIDTH
                    ),
                ),
            )

            line.adjudication_left_interval_index = left_index
            line.setZValue(1000)

            line.setToolTip(
                (
                    "Click to select this boundary. Drag to adjust it, keeping "
                    f"both intervals at least {minimum_duration:g} second(s). "
                    "Remove Selected Boundary merges the neighboring intervals."
                )
                if valid_drag_range
                else (
                    "Click to select this boundary for removal. Dragging is "
                    "unavailable because the neighboring intervals cannot both "
                    f"remain at least {minimum_duration:g} second(s). "
                    "Merge short fragments first."
                )
            )

            line.boundarySelected.connect(
                self.select_adjudication_boundary
            )

            # sigDragged fires during mouse dragging, not ordinary selection/redrawing.
            line.sigDragged.connect(
                self.update_adjudication_boundary_drag_guides
            )

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
        Commit a dragged final boundary and remove its temporary waveform guides.

        Guides are removed whether the edit succeeds or is rejected.
        """
        started = perf_counter()

        try:
            self._finish_adjudication_boundary_drag_impl(
                left_index,
                line,
            )

        except Exception as exc:
            print("[ADJ-UI] Boundary movement failed:", repr(exc))

            # Restore handles to the final interval data after a rejected drag.
            self.draw_adjudication_boundary_handles()

            self.show_adjudication_error(
                "Boundary Change Failed",
                str(exc),
            )

        finally:
            self.clear_adjudication_boundary_drag_guides()

            self._adjudication_perf_log(
                "finish_adjudication_boundary_drag",
                perf_counter() - started,
            )


    def _finish_adjudication_boundary_drag_impl(
        self,
        left_index: int,
        line: pg.InfiniteLine,
    ) -> None:
        """
        Commit a shared final boundary while enforcing the interval minimum.

        Both neighboring intervals must remain at least
        MINIMUM_VALID_INTERVAL_SEC long. Limits depend on their outer endpoints,
        not their current durations, so dragging remains reversible.
        """
        comparison = self.adjudication_comparison

        if comparison is None:
            return

        intervals = comparison.prefilled_intervals

        if not 0 <= left_index < len(intervals) - 1:
            raise ValueError("The selected boundary is no longer available.")

        left = intervals[left_index]
        right = intervals[left_index + 1]
        original_time = float(left.end)

        if self.adjudication_complete:
            line.setValue(original_time)
            raise ValueError("Reopen the completed adjudication before editing.")

        if self.adjudication_caliper_adjust_active:
            line.setValue(original_time)
            raise ValueError("Turn caliper interaction modes off first.")

        if self.adjudication_pending_split_index is not None:
            line.setValue(original_time)
            raise ValueError("Finish or cancel Add Boundary first.")

        if self.adjudication_sidebar_has_unapplied_changes():
            line.setValue(original_time)
            raise ValueError(
                "Apply pending final-label changes before moving a boundary."
            )

        new_time = float(line.value())

        if not np.isfinite(new_time):
            line.setValue(original_time)
            raise ValueError("The boundary position is not finite.")

        minimum_duration = float(MINIMUM_VALID_INTERVAL_SEC)
        lower_bound = float(left.start + minimum_duration)
        upper_bound = float(right.end - minimum_duration)

        if lower_bound > upper_bound:
            line.setValue(original_time)
            raise ValueError(
                "These neighboring intervals do not have enough combined "
                "duration to preserve the minimum. Merge short fragments first."
            )

        # Clamp to fixed limits: either neighboring interval may reach exactly
        # the minimum, but neither may become shorter.
        new_time = max(lower_bound, min(new_time, upper_bound))

        if (
            new_time - left.start < minimum_duration
            or right.end - new_time < minimum_duration
        ):
            line.setValue(original_time)
            raise ValueError(
                f"Both intervals must remain at least "
                f"{minimum_duration:g} second(s) long."
            )

        if new_time == original_time:
            line.setValue(original_time)
            return

        updated_at = utc_now_iso()

        # Commit both endpoints together to preserve continuity.
        left.end = new_time
        right.start = new_time
        left.adjudication_updated_at = updated_at
        right.adjudication_updated_at = updated_at

        self.invalidate_adjudication_resolutions_in_range(
            float(left.start),
            float(right.end),
        )

        self.adjudication_dirty = True

        self._clear_adjudication_selection_graphics()
        self.draw_adjudication_timelines()
        self.populate_adjudication_table()
        self.select_adjudication_interval(left_index)

        # Keep the moved boundary explicitly selected after graphics are rebuilt.
        self.adjudication_selected_boundary_index = left_index
        self.draw_adjudication_boundary_handles()
        self.update_adjudication_boundary_controls()
        self.update_adjudication_navigation_controls()

        self.adjudication_status_label.setText(
            "Final boundary updated. Both intervals remain at least "
            f"{minimum_duration:g} second(s). Save Draft to preserve the change."
        )
        self.adjudication_save_status.setText("Unsaved boundary changes.")


    def select_adjudication_boundary(
        self,
        line: SelectableAdjudicationBoundary,
    ) -> None:
        """
        Select one exact internal final boundary with timing diagnostics.

        Selection does not modify intervals or resolution state.
        """
        started = perf_counter()

        try:
            self._select_adjudication_boundary_impl(line)
        except Exception as exc:
            print("[ADJ-UI] Boundary selection failed:", repr(exc))
            self.show_adjudication_error(
                "Boundary Selection Failed",
                str(exc),
            )
        finally:
            self._adjudication_perf_log(
                "select_adjudication_boundary",
                perf_counter() - started,
            )


    def _select_adjudication_boundary_impl(
        self,
        line: SelectableAdjudicationBoundary,
    ) -> None:
        """Select the boundary and display its left neighboring interval."""
        if (
            self.adjudication_complete
            or self.adjudication_caliper_adjust_active
            or self.adjudication_pending_split_index is not None
        ):
            return

        if self.adjudication_sidebar_has_unapplied_changes():
            raise ValueError(
                "Apply pending label changes before selecting a boundary."
            )

        index = int(line.adjudication_left_interval_index)
        comparison = self.adjudication_comparison

        if comparison is None or not (
            0 <= index < len(comparison.prefilled_intervals) - 1
        ):
            return

        # Selecting the left interval gives useful sidebar context.
        self.select_adjudication_interval(index)

        self.adjudication_selected_boundary_index = index
        self.draw_adjudication_boundary_handles()
        self.update_adjudication_boundary_controls()

        boundary_time = comparison.prefilled_intervals[index].end
        relative_time = boundary_time - self.adjudication_waveform_start

        self.adjudication_status_label.setText(
            f"Boundary selected at {relative_time:.3f} seconds. "
            "Remove Selected Boundary will merge its two neighboring intervals."
        )


    def clear_adjudication_boundary_selection(self) -> None:
        """Clear persistent boundary selection without changing timeline data."""
        if self.adjudication_selected_boundary_index is None:
            return

        self.adjudication_selected_boundary_index = None
        self.draw_adjudication_boundary_handles()
        self.update_adjudication_boundary_controls()


    def update_adjudication_boundary_drag_guides(
        self,
        moved_line: pg.InfiniteLine,
    ) -> None:
        """
        Show the dragged boundary's current time across every waveform plot.

        Existing guides are repositioned rather than recreated for each movement.
        No final data or resolution state is modified here.
        """
        position = float(moved_line.value())

        if not np.isfinite(position):
            return

        if not self.adjudication_boundary_drag_guides:
            pen = pg.mkPen(
                ADJUDICATION_DRAG_GUIDE_COLOR,
                width=ADJUDICATION_DRAG_GUIDE_WIDTH,
                style=Qt.DotLine,
            )

            for plot in self.adjudication_waveform_plots:
                guide = pg.InfiniteLine(
                    pos=position,
                    angle=90,
                    movable=False,
                    pen=pen,
                )

                # Above overlays and selection shading.
                guide.setZValue(2000)
                plot.addItem(guide, ignoreBounds=True)

                self.adjudication_boundary_drag_guides.append(
                    (plot, guide)
                )

        else:
            for _plot, guide in self.adjudication_boundary_drag_guides:
                guide.setValue(position)


    def clear_adjudication_boundary_drag_guides(self) -> None:
        """
        Remove temporary drag guides after release, cancellation, or record change.
        """
        for plot, guide in self.adjudication_boundary_drag_guides:
            if guide.scene() is not None:
                plot.removeItem(guide)

        self.adjudication_boundary_drag_guides = []


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
        self.refresh_loaded_adjudication_record_status()


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
        self.refresh_loaded_adjudication_record_status()


    # =========================================================================
    # Draft autosave
    # =========================================================================

    def autosave_current_adjudication(self) -> None:
        """
        Automatically save changed draft work without a blocking dialog.

        Completed sessions, unapplied sidebar changes, and pending boundary
        placement are not saved automatically.

        Save failures retain dirty state and are reported in the sidebar and
        terminal. The next timer interval can retry.
        """
        if getattr(self, "adjudication_autosave_in_progress", False):
            return

        started = perf_counter()
        self.adjudication_autosave_in_progress = True

        try:
            self._autosave_current_adjudication_impl()

        except Exception as exc:
            print(
                "[ADJ-UI] Autosave failed:",
                type(exc).__name__,
                exc,
            )

            # Do not clear dirty state or display a success message.
            self.adjudication_save_status.setText(
                "Autosave failed. Work remains unsaved; retry Save Draft."
            )
            self.adjudication_save_status.setToolTip(
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            self.adjudication_autosave_in_progress = False

            self._adjudication_perf_log(
                "autosave_current_adjudication",
                perf_counter() - started,
            )


    def _autosave_current_adjudication_impl(self) -> None:
        """
        Save an eligible draft using the existing verified persistence path.

        The loaded session determines the record and reviewer. Dropdown changes
        do not redirect the save.
        """
        if self.adjudication_comparison is None:
            return

        if self.adjudication_complete:
            return

        if not self.adjudication_dirty:
            return

        if self.adjudication_pending_split_index is not None:
            self.adjudication_save_status.setText(
                "Autosave deferred: finish or cancel boundary placement."
            )
            return

        if self.adjudication_sidebar_has_unapplied_changes():
            self.adjudication_save_status.setText(
                "Autosave deferred: click Apply Final Label first."
            )
            return

        # Reuse draft verification, reopened-history handling, and single-record
        # status refresh. Do not call the public manual-save wrapper because it
        # opens an error dialog on failure.
        self._save_current_adjudication_draft_impl()

        # The shared implementation clears dirty state only after verified saving.
        self.adjudication_save_status.setText(
            "Draft autosaved successfully."
        )

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
        # The previous completed files remain on disk until draft saving succeeds.
        self.refresh_loaded_adjudication_record_status(
            status_override="Draft"
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
        Display a compact error with selectable, scrollable full details.

        Long network paths are placed in the expandable details panel rather
        than forcing the dialog beyond the screen.
        """
        full_message = str(message)

        # Preserve the complete error in terminal output as well.
        print(f"[ADJ-UI] {title}: {full_message}")

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.PlainText)

        dialog.setText(title)
        dialog.setInformativeText(
            "The operation could not be completed. "
            "Select Show Details to view and copy the complete error."
        )
        dialog.setDetailedText(full_message)

        dialog.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
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
            QMessageBox QTextEdit {
                color: #00274C;
                background-color: #FFFFFF;
                min-width: 420px;
                min-height: 180px;
            }
            QMessageBox QPushButton {
                background-color: #00274C;
                color: #FFCB05;
                padding: 6px 12px;
            }
            """
        )

        dialog.exec_()