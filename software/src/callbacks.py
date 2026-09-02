import os
import numpy as np
import pandas as pd
from datetime import datetime
from processing import list_subjects, load_waveforms_for_subject, get_code_time_bounds, get_events_for_window, datetime_string_to_seconds_since_1970
from PyQt5.QtWidgets import (
    QTableWidgetItem,
    QMessageBox,
    QDialog,
    QVBoxLayout,
    QLabel,
    QRadioButton,
    QTextEdit,
    QDialogButtonBox,
)
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
import pyqtgraph as pg

# Testing performance import
from time import perf_counter

UM_MAIZE = "#FFCB05"
UM_BLUE = "#00274C"
UM_ACCENT = "#285680"
UM_WHITE = "#FFFFFF"
UM_RED = "#D50032"
COMPLETION_GREEN = "#199E40"


# ---------------------------------------------------------------------------
# Waveforms Present
# ---------------------------------------------------------------------------

WAVEFORM_PLOT_ORDER = ["I", "II", "III", "V", "AVF", "AVL", "CHEST_IMPEDANCE"]

# ---------------------------------------------------------------------------
# Color Assignment
# ---------------------------------------------------------------------------

LABEL_COLORS = {
    "Normal Heart Rhythm": (0, 158, 96, 60),
    "Sinus tachycardia": (255, 128, 0, 60),
    "Bradycardia": (0, 0, 200, 60),
    "Atrial Flutter": (255, 0, 128, 60),
    "Atrial Fibrillation": (200, 0, 0, 60),
    "Ventricular Tachycardia": (204, 102, 0, 60),
    "Ventricular Fibrillation": (153, 102, 51, 60),
    "Unable to Determine": (130, 130, 130, 60),
    "Other": (204, 204, 0, 60),
    # Add others as needed
}
DEFAULT_COLOR = "LightGray"

# ---------------------------------------------------------------------------
# Performance diagnostics Configurable
# ---------------------------------------------------------------------------

PERF_DIAGNOSTICS_ENABLED = True

# ---------------------------------------------------------------------------

class RelativeAxis(pg.AxisItem):
    def __init__(self, t0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t0 = t0

    def tickStrings(self, values, scale, spacing):
        # Display ticks as seconds from the recording start
        return [f"{v - self.t0:.1f}" for v in values]

class AnnotationAppCallbacks:

    # ---------------------------------------------------------------------------
    # Performance diagnostics Functionality (Private)
    # ---------------------------------------------------------------------------

    def _perf_log(self, operation, elapsed_seconds, **details):
        """
        Print a standardized performance diagnostic line.
        """
        if not PERF_DIAGNOSTICS_ENABLED:
            return

        detail_text = " ".join(
            f"{key}={value}"
            for key, value in details.items()
        )

        if detail_text:
            detail_text = f" | {detail_text}"

        print(
            f"[PERF] {operation}: "
            f"{elapsed_seconds:.4f} sec"
            f"{detail_text}"
        )


    def _format_bytes(self, byte_count):
        """
        Convert a byte count into a readable string.
        """
        try:
            value = float(byte_count)
        except (TypeError, ValueError):
            return "unknown"

        units = ["B", "KB", "MB", "GB", "TB"]

        for unit in units:
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.2f} {unit}"

            value /= 1024.0

        return f"{value:.2f} TB"


    def _get_array_nbytes(self, value):
        """
        Return NumPy storage size for an array-like value.
        """
        if value is None:
            return 0

        try:
            return int(np.asarray(value).nbytes)
        except Exception:
            return 0


    def _print_waveform_memory_summary(self):
        """
        Print point counts and approximate NumPy memory usage for loaded waveforms.
        """
        if not PERF_DIAGNOSTICS_ENABLED:
            return

        time_axis = getattr(self, "time_axis", None)
        leads = getattr(self, "leads_ds", None) or []
        lead_names = getattr(self, "lead_names", None) or []
        time_axes_by_lead = getattr(self, "time_axes_by_lead", None) or []

        time_points = 0
        time_bytes = 0

        if time_axis is not None:
            try:
                time_points = len(time_axis)
            except Exception:
                time_points = 0

            time_bytes = self._get_array_nbytes(time_axis)

        total_lead_points = 0
        total_lead_bytes = 0

        print("[PERF] ----- Loaded waveform summary -----")
        print(
            f"[PERF] Global time axis: "
            f"points={time_points} "
            f"memory={self._format_bytes(time_bytes)}"
        )

        for index, lead in enumerate(leads):
            name = (
                lead_names[index]
                if index < len(lead_names)
                else f"Signal {index + 1}"
            )

            if lead is None:
                lead_points = 0
                lead_bytes = 0
            else:
                try:
                    lead_points = len(lead)
                except Exception:
                    lead_points = 0

                lead_bytes = self._get_array_nbytes(lead)

            total_lead_points += lead_points
            total_lead_bytes += lead_bytes

            if index < len(time_axes_by_lead):
                lead_time_axis = time_axes_by_lead[index]

                try:
                    lead_time_points = len(lead_time_axis)
                except Exception:
                    lead_time_points = 0
            else:
                lead_time_points = time_points

            print(
                f"[PERF] Lead {index}: "
                f"name={name} "
                f"signal_points={lead_points} "
                f"time_points={lead_time_points} "
                f"memory={self._format_bytes(lead_bytes)}"
            )

        numpy_total = time_bytes + total_lead_bytes

        print(
            f"[PERF] Waveform totals: "
            f"lead_points={total_lead_points} "
            f"lead_memory={self._format_bytes(total_lead_bytes)} "
            f"time_plus_leads={self._format_bytes(numpy_total)}"
        )

        data_store = getattr(self, "data_store", {})

        if isinstance(data_store, dict):
            stored_time = data_store.get("time")
            stored_leads = data_store.get("leads")

            print(
                f"[PERF] data_store waveform copy: "
                f"time_type={type(stored_time).__name__} "
                f"leads_type={type(stored_leads).__name__}"
            )

            if isinstance(stored_time, list):
                print(
                    f"[PERF] WARNING: data_store['time'] is a Python list "
                    f"containing {len(stored_time)} values."
                )

            if isinstance(stored_leads, list):
                stored_lead_values = 0

                for lead in stored_leads:
                    if isinstance(lead, list):
                        stored_lead_values += len(lead)

                print(
                    f"[PERF] WARNING: data_store['leads'] contains "
                    f"{stored_lead_values} Python-list values."
                )

        print("[PERF] -----------------------------------")


    def _get_plot_item_counts(self):
        """
        Return counts of graphics items currently attached to waveform plots.
        """
        counts = {
            "total": 0,
            "data_items": 0,
            "regions": 0,
            "text_items": 0,
            "infinite_lines": 0,
        }

        for plot in getattr(self, "waveform_plots", []):
            try:
                items = list(plot.items())
            except Exception:
                continue

            counts["total"] += len(items)

            for item in items:
                if isinstance(item, pg.PlotDataItem):
                    counts["data_items"] += 1
                elif isinstance(item, pg.LinearRegionItem):
                    counts["regions"] += 1
                elif isinstance(item, pg.TextItem):
                    counts["text_items"] += 1
                elif isinstance(item, pg.InfiniteLine):
                    counts["infinite_lines"] += 1

        return counts


    def _print_plot_performance_summary(self):
        """
        Print graphics counts and PyQtGraph optimization state.
        """
        if not PERF_DIAGNOSTICS_ENABLED:
            return

        counts = self._get_plot_item_counts()

        print(
            "[PERF] Plot graphics: "
            f"total={counts['total']} "
            f"curves={counts['data_items']} "
            f"regions={counts['regions']} "
            f"text={counts['text_items']} "
            f"lines={counts['infinite_lines']}"
        )

        for plot_index, plot in enumerate(
            getattr(self, "waveform_plots", [])
        ):
            try:
                data_items = plot.listDataItems()
            except Exception:
                data_items = []

            for curve_index, curve in enumerate(data_items):
                opts = getattr(curve, "opts", {})

                print(
                    f"[PERF] Plot {plot_index} curve {curve_index}: "
                    f"clipToView={opts.get('clipToView', 'unknown')} "
                    f"autoDownsample={opts.get('autoDownsample', 'unknown')} "
                    f"downsample={opts.get('downsample', 'unknown')} "
                    f"downsampleMethod={opts.get('downsampleMethod', 'unknown')}"
                )

    # ---------------------------------------------------------------------------


    def set_base_folder(self):
        folder_path = self.folder_input.text().strip().strip('"').strip("'")
        folder_path = os.path.normpath(folder_path)

        print("SET FOLDER CLICKED", folder_path)

        if not folder_path or not os.path.isdir(folder_path):
            self.base_folder = ""
            self.folder_status.setText("❌ Invalid folder.")
            return

        previous_base_folder = getattr(self, "base_folder", "")
        self.base_folder = folder_path

        self.folder_status.setText(
            f"📂 Base folder set: {folder_path}"
        )

        # Invalidate cached discovery records only when the selected base folder
        # changes. Clicking Set Folder again forces a fresh discovery scan.
        if (
            previous_base_folder != folder_path
            or getattr(self, "_waveform_cache_base_folder", None) != folder_path
        ):
            self._waveform_record_cache = []
            self._waveform_cache_base_folder = None

        self.update_subject_dropdown(force_full_scan=True)

    # ------------------------------------------------------------------
    # Subject Search and Dropdown Population
    # ------------------------------------------------------------------

    def update_subject_dropdown(self, force_full_scan=False):
        """
        Timed wrapper around cached subject discovery, annotation-status checks,
        and dropdown reconstruction.

        Parameters
        ----------
        force_full_scan : bool
            If True, rediscover waveform records from the base folder.
            If False, reuse the in-memory waveform-record cache when available.
        """
        start_time = perf_counter()

        try:
            return self._update_subject_dropdown_impl(
                force_full_scan=force_full_scan,
            )
        finally:
            elapsed = perf_counter() - start_time

            base_folder = getattr(self, "base_folder", "")
            user_name = self.get_user_name()

            try:
                record_count = self.subject_dropdown.count()
            except Exception:
                record_count = "unknown"

            cache_available = bool(
                getattr(self, "_waveform_record_cache", [])
            )

            self._perf_log(
                "update_subject_dropdown",
                elapsed,
                records=record_count,
                user=user_name,
                force_full_scan=force_full_scan,
                cache_available=cache_available,
                base_folder=base_folder,
            )


    def _update_subject_dropdown_impl(self, force_full_scan=False):
        """
        Populate the subject dropdown using cached waveform discovery records.

        Static waveform discovery is performed only when:

        - a base folder is first selected,
        - a different base folder is selected,
        - force_full_scan is True.

        Annotation status is checked separately for the active user.
        """
        base_folder = getattr(self, "base_folder", None)
        combo = self.subject_dropdown

        if not base_folder or not os.path.isdir(base_folder):
            combo.clear()
            combo.setDisabled(True)
            return

        user_name = self.get_user_name()

        if user_name is not None:
            user_name = str(user_name).strip()
        else:
            user_name = ""

        self.user_name = user_name

        normalized_base_folder = os.path.normcase(
            os.path.abspath(base_folder)
        )

        cached_base_folder = getattr(
            self,
            "_waveform_cache_base_folder",
            None,
        )

        cache_valid = (
            bool(getattr(self, "_waveform_record_cache", []))
            and cached_base_folder == normalized_base_folder
        )

        # Preserve the selected waveform record while rebuilding labels.
        old_record = self.get_selected_subject_record()
        old_key = self.get_record_refresh_key(old_record)

        # --------------------------------------------------------------
        # Full waveform discovery
        # --------------------------------------------------------------
        if force_full_scan or not cache_valid:
            discovery_start = perf_counter()

            discovered_records = list_subjects(
                base_folder,
                user_name=user_name,
            )

            discovery_elapsed = perf_counter() - discovery_start

            # Store independent dictionaries in the session cache.
            self._waveform_record_cache = [
                dict(record)
                for record in discovered_records
                if isinstance(record, dict)
            ]

            self._waveform_cache_base_folder = normalized_base_folder

            self._perf_log(
                "discover_waveform_records",
                discovery_elapsed,
                records=len(self._waveform_record_cache),
                base_folder=base_folder,
            )
        else:
            self._perf_log(
                "discover_waveform_records CACHE_HIT",
                0.0,
                records=len(self._waveform_record_cache),
                base_folder=base_folder,
            )

        # --------------------------------------------------------------
        # Refresh only user-specific annotation status.
        # This does not rediscover or reopen waveform files.
        # --------------------------------------------------------------
        annotation_status_start = perf_counter()

        if user_name:
            for record in self._waveform_record_cache:
                self.refresh_record_annotation_status(
                    record,
                    user_name=user_name,
                )
        else:
            for record in self._waveform_record_cache:
                record["n_annotations"] = 0
                record["n_complete_annotations"] = 0
                record["has_annotations"] = False

        annotation_status_elapsed = (
            perf_counter() - annotation_status_start
        )

        self._perf_log(
            "refresh_annotation_status_all_records",
            annotation_status_elapsed,
            records=len(self._waveform_record_cache),
            user=user_name,
        )

        # --------------------------------------------------------------
        # Populate dropdown from cached records.
        # --------------------------------------------------------------
        populate_start = perf_counter()

        combo.blockSignals(True)
        combo.clear()
        combo.setDisabled(True)

        selected_index = -1

        for record in self._waveform_record_cache:
            label = self.get_subject_dropdown_label(record)

            combo.addItem(
                label,
                userData=record,
            )

            index = combo.count() - 1
            record_key = self.get_record_refresh_key(record)

            if old_key and record_key == old_key:
                selected_index = index

            tooltip = self.get_record_tooltip(record)

            if tooltip:
                combo.setItemData(
                    index,
                    tooltip,
                    Qt.ToolTipRole,
                )

        if selected_index >= 0:
            combo.setCurrentIndex(selected_index)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

        combo.setDisabled(combo.count() == 0)
        combo.blockSignals(False)

        populate_elapsed = perf_counter() - populate_start

        self._perf_log(
            "populate_subject_dropdown_from_cache",
            populate_elapsed,
            records=combo.count(),
        )

        print(f"FOUND {combo.count()} waveform records")
        print(f"COMPLETION USER: {user_name}")

        for record in self._waveform_record_cache[:5]:
            print("SUBJECT RECORD:", record)


    def get_record_refresh_key(self, record):
        """
        Return a stable key for a subject/waveform record so we can preserve
        selection after rebuilding the subject dropdown.
        """
        if not isinstance(record, dict):
            return None

        return (
            record.get("h5_path")
            or record.get("csv_path")
            or record.get("output_path")
            or record.get("name")
        )


    def get_annotation_filenames_for_record(self, record, user_name):
        """
        Return partial and complete annotation filenames for a specific cached
        waveform record and user.

        This avoids depending on the currently selected dropdown item.
        """
        if not isinstance(record, dict):
            return None, None

        subject = str(record.get("subject", "") or "").strip()
        file_tag = str(record.get("file_tag", "") or "").strip()
        user_name = str(user_name or "").strip()

        if not subject or not user_name:
            return None, None

        if file_tag:
            base = f"annotations_{subject}_{file_tag}_{user_name}"
        else:
            base = f"annotations_{subject}_{user_name}"

        return (
            f"{base}.csv",
            f"{base}_COMPLETE.csv",
        )


    def get_annotation_output_folder_for_record(self, record, user_name):
        """
        Return the user-specific annotation folder for a cached waveform record.
        """
        if not isinstance(record, dict):
            return None

        user_name = str(user_name or "").strip()

        if not user_name:
            return None

        output_path = record.get("output_path", "")

        if output_path:
            return os.path.join(
                output_path,
                user_name,
            )

        base_folder = getattr(self, "base_folder", None)
        subject = record.get("subject", "")

        if base_folder and subject:
            return os.path.join(
                base_folder,
                subject,
                "output",
                user_name,
            )

        return None


    def refresh_record_annotation_status(self, record, user_name=None):
        """
        Refresh annotation counts for one cached waveform record.

        This inspects only the known user output folder. It does not rescan the
        waveform hierarchy or reopen waveform files.

        Returns
        -------
        dict
            The updated record dictionary.
        """
        if not isinstance(record, dict):
            return record

        if user_name is None:
            user_name = self.get_user_name()

        user_name = str(user_name or "").strip()

        if not user_name:
            record["n_annotations"] = 0
            record["n_complete_annotations"] = 0
            record["has_annotations"] = False
            return record

        output_folder = self.get_annotation_output_folder_for_record(
            record,
            user_name,
        )

        partial_filename, complete_filename = (
            self.get_annotation_filenames_for_record(
                record,
                user_name,
            )
        )

        if (
            not output_folder
            or not partial_filename
            or not complete_filename
        ):
            record["n_annotations"] = 0
            record["n_complete_annotations"] = 0
            record["has_annotations"] = False
            return record

        partial_exists = False
        complete_exists = False

        try:
            with os.scandir(output_folder) as entries:
                filenames = {
                    entry.name
                    for entry in entries
                    if entry.is_file()
                }

            partial_exists = partial_filename in filenames
            complete_exists = complete_filename in filenames

        except FileNotFoundError:
            pass

        except NotADirectoryError:
            pass

        except PermissionError as exc:
            print(
                "WARNING: Could not inspect annotation folder "
                f"{output_folder}: {exc}"
            )

        except OSError as exc:
            print(
                "WARNING: Could not inspect annotation folder "
                f"{output_folder}: {exc}"
            )

        total_annotations = int(partial_exists) + int(complete_exists)
        complete_annotations = int(complete_exists)

        record["completion_user"] = user_name
        record["n_annotations"] = total_annotations
        record["n_complete_annotations"] = complete_annotations
        record["has_annotations"] = total_annotations > 0

        return record


    def get_subject_dropdown_label(self, record):
        """
        Build the visible dropdown label for one waveform record.
        """
        total_annotations = int(
            record.get("n_annotations", 0) or 0
        )
        complete_annotations = int(
            record.get("n_complete_annotations", 0) or 0
        )

        if total_annotations == 0:
            icon = "⭕"
        elif complete_annotations == total_annotations:
            icon = "✅"
        else:
            icon = "🟡"

        return (
            f"{icon} {record.get('name', '')} "
            f"({complete_annotations}/{total_annotations} complete)"
        )


    def get_record_tooltip(self, record):
        """
        Return a source-path tooltip for one waveform record.
        """
        if not isinstance(record, dict):
            return ""

        kind = record.get("kind", "")

        if kind == "h5":
            return str(record.get("h5_path", "") or "")

        if kind == "csv":
            return str(record.get("csv_path", "") or "")

        if kind == "h5_multi":
            h5_paths = record.get("h5_paths", {})

            if isinstance(h5_paths, dict):
                return "\n".join(
                    f"{namespace}: {path}"
                    for namespace, path in sorted(h5_paths.items())
                )

        return str(
            record.get("source_path", "")
            or record.get("encounter_path", "")
            or ""
        )


    def refresh_selected_record_annotation_status(self):
        """
        Refresh annotation status for only the currently selected waveform record.

        This avoids rebuilding the full dropdown and avoids rescanning all records.
        """
        start_time = perf_counter()

        record = self.get_selected_subject_record()
        user_name = self.get_user_name()

        if not isinstance(record, dict) or not user_name:
            return

        record_key = self.get_record_refresh_key(record)

        updated_record = None

        for cached_record in getattr(
            self,
            "_waveform_record_cache",
            [],
        ):
            if self.get_record_refresh_key(cached_record) == record_key:
                self.refresh_record_annotation_status(
                    cached_record,
                    user_name=user_name,
                )
                updated_record = cached_record
                break

        if updated_record is None:
            self.refresh_record_annotation_status(
                record,
                user_name=user_name,
            )
            updated_record = record

        index = self.subject_dropdown.currentIndex()

        if index >= 0:
            self.subject_dropdown.setItemText(
                index,
                self.get_subject_dropdown_label(updated_record),
            )

            self.subject_dropdown.setItemData(
                index,
                updated_record,
                Qt.UserRole,
            )

            tooltip = self.get_record_tooltip(updated_record)

            if tooltip:
                self.subject_dropdown.setItemData(
                    index,
                    tooltip,
                    Qt.ToolTipRole,
                )

        self.current_subject_record = updated_record

        elapsed = perf_counter() - start_time

        self._perf_log(
            "refresh_selected_record_annotation_status",
            elapsed,
            user=user_name,
            record=updated_record.get("name", ""),
        )


    def refresh_subject_dropdown_preserve_selection(self):
        """
        Timed wrapper around cached completion-count refresh and selection
        restoration.
        """
        start_time = perf_counter()

        try:
            return self._refresh_subject_dropdown_preserve_selection_impl()
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "refresh_subject_dropdown_preserve_selection",
                elapsed,
            )


    def _refresh_subject_dropdown_preserve_selection_impl(self):
        """
        Refresh all user-specific annotation counts while reusing cached waveform
        discovery records.

        This does not rerun recursive waveform discovery unless no valid cache exists.
        """
        old_record = self.get_selected_subject_record()
        old_key = self.get_record_refresh_key(old_record)

        self.update_subject_dropdown(
            force_full_scan=False,
        )

        if not old_key:
            return

        for index in range(self.subject_dropdown.count()):
            record = self.subject_dropdown.itemData(index)
            new_key = self.get_record_refresh_key(record)

            if new_key != old_key:
                continue

            self.subject_dropdown.setCurrentIndex(index)

            if isinstance(record, dict):
                self.current_subject_record = record
                self.current_subject = record.get("subject", "")
                self.current_encounter = record.get("encounter", "")
                self.current_namespace = record.get("namespace", "")
                self.current_file_tag = record.get("file_tag", "")
                self.current_output_path = record.get("output_path", "")
                self.current_h5_path = record.get("h5_path", "")

            break


    def handle_user_changed(self):
            """
            Timed wrapper around changing of user
            """
            start_time = perf_counter()
    
            try:
                return self._handle_user_changed_impl()
            finally:
                elapsed = perf_counter() - start_time
    
                self._perf_log(
                    "handle_user_changed",
                    elapsed,
                )


    def _handle_user_changed_impl(self, *args):
        """
        Called when the selected user changes.

        Reuse cached waveform records and refresh only the user-specific annotation
        status for those records.
        """
        user_name = self.get_user_name()

        if user_name is not None:
            user_name = str(user_name).strip()
        else:
            user_name = ""

        self.user_name = user_name

        print(f"USER CHANGED TO: {self.user_name}")

        # Reuse cached waveform discovery records.
        # This checks annotation status for the new user without reopening waveform
        # files or recursively rediscovering the waveform hierarchy.
        self.update_subject_dropdown(
            force_full_scan=False,
        )

        # Clear annotations displayed for the previous user.
        self.annotations = []
        self.waveform_complete = False
        self.terminal_event_status = ""
        self.terminal_event_comment = ""
        self.current_marker = None

        if (
            hasattr(self, "time_axis")
            and self.time_axis is not None
            and len(self.time_axis) > 0
        ):
            self.last_mark = float(self.time_axis[0])
        else:
            self.last_mark = None

        self.update_table_data()
        self.update_waveform_and_mark()
        self.update_sidebar_ui()
        self.update_finalize_button_state()

        self.mark_warning.setText(
            f"User changed to '{self.user_name}'. "
            "Load annotations for this user if needed."
        )
        self.mark_warning.setWordWrap(True)
        self.mark_warning.setStyleSheet(
            "color: #285680; font-size: 13px; font-weight: bold;"
        )

    # ------------------------------------------------------------------
    # Establish Plotting Parameter
    # ------------------------------------------------------------------

    def get_global_valid_time_range(self):
        """
        Return x/time range where at least one loaded lead has finite data.
        Uses per-lead time axes if available.
        """
        if not hasattr(self, "leads_ds") or self.leads_ds is None:
            return None

        starts = []
        stops = []

        for i, sig in enumerate(self.leads_ds):
            if sig is None:
                continue

            y = np.asarray(sig, dtype=float)

            if y.size == 0:
                continue

            if hasattr(self, "time_axes_by_lead") and self.time_axes_by_lead is not None and i < len(self.time_axes_by_lead):
                x = np.asarray(self.time_axes_by_lead[i], dtype=float)
            else:
                x = np.asarray(self.time_axis, dtype=float)

            n = min(len(x), len(y))

            if n <= 0:
                continue

            x = x[:n]
            y = y[:n]

            valid = np.isfinite(x) & np.isfinite(y)

            if np.any(valid):
                starts.append(float(x[valid][0]))
                stops.append(float(x[valid][-1]))

        if starts and stops:
            return min(starts), max(stops)

        # fallback to loaded global range
        return self.get_loaded_global_time_range()


    def get_safe_y_range(self, sig, percentile_low=0.5, percentile_high=99.5):
        """
        Robustly compute a valid y-range for a signal.

        Returns
        -------
        tuple
            y_min, y_max, has_data
        """
        if sig is None:
            return -1.0, 1.0, False

        sig = np.asarray(sig, dtype=float)

        if sig.size == 0:
            return -1.0, 1.0, False

        finite_sig = sig[np.isfinite(sig)]

        if finite_sig.size == 0:
            return -1.0, 1.0, False

        try:
            y_lo, y_hi = np.nanpercentile(
                finite_sig,
                [percentile_low, percentile_high],
            )
        except Exception:
            return -1.0, 1.0, False

        if not np.isfinite(y_lo) or not np.isfinite(y_hi):
            return -1.0, 1.0, False

        # Current style: center range around zero.
        half_span = max(abs(float(y_lo)), abs(float(y_hi)))

        if not np.isfinite(half_span) or half_span <= 0:
            center = float(np.nanmedian(finite_sig))

            if not np.isfinite(center):
                center = 0.0

            y_min = center - 1.0
            y_max = center + 1.0
            return y_min, y_max, True

        margin = 0.1 * half_span
        y_min = -half_span - margin
        y_max = half_span + margin

        if not np.isfinite(y_min) or not np.isfinite(y_max) or y_min >= y_max:
            return -1.0, 1.0, False

        return float(y_min), float(y_max), True


    def add_no_data_label(self, plot, text="No data"):
        """
        Add a no-data label to a pyqtgraph plot.
        """
        label = pg.TextItem(
            text=text,
            color=(140, 140, 140),
            anchor=(0.5, 0.5),
        )

        label.is_no_data_label = True
        plot.addItem(label)

        try:
            x_min, x_max = plot.viewRange()[0]
            y_min, y_max = plot.viewRange()[1]
            label.setPos((x_min + x_max) / 2.0, (y_min + y_max) / 2.0)
        except Exception:
            label.setPos(0, 0)

        return label

    # ------------------------------------------------------------------
    # Waveform Y-Axis Scaling
    # ------------------------------------------------------------------

    def autoscale_y(self, plot, signal):
        """
        Autoscale the y-axis of the given PlotWidget to fit the central 99% of signal values,
        avoiding huge artifacts or outliers.
        
        Parameters:
        - plot: The pyqtgraph PlotWidget to set the Y range.
        - signal: The 1D numpy array of waveform values.
        """
        y_min, y_max, has_data = self.get_safe_y_range(signal)

        if has_data:
            plot.setYRange(y_min, y_max, padding=0)
        else:
            plot.setYRange(-1.0, 1.0, padding=0)


    def adjust_y_scale(self, plot_idx, zoom="up"):
        """
        Timed wrapper around manual Y-axis zoom.
        """
        start_time = perf_counter()

        try:
            return self._adjust_y_scale_impl(
                plot_idx,
                zoom=zoom,
            )
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "adjust_y_scale",
                elapsed,
                plot_idx=plot_idx,
                zoom=zoom,
            )


    def _adjust_y_scale_impl(self, plot_idx, zoom="up"):
        """
        Adjusts the Y-axis scaling of the selected PlotWidget by zooming in or out.
        Zooms in by shrinking Y range (zoom="up"), or zooms out by expanding (zoom="down").
        
        Parameters:
        - plot_idx: Index of the PlotWidget to adjust
        - zoom: "up" to zoom in (shrink), "down" to zoom out (expand)
        """
        self.disable_auto_y_for_plot(plot_idx)
        plt = self.waveform_plots[plot_idx]
        y_min, y_max = plt.viewRange()[1]
        center = (y_min + y_max) / 2
        span = (y_max - y_min) or 1.0
        if zoom == "in":
            new_span = span * 0.8  # Zoom in
        elif zoom == "out":
            new_span = span * 1.25 # Zoom out
        else:
            new_span = span
        new_min = center - new_span / 2
        new_max = center + new_span / 2
        plt.setYRange(new_min, new_max, padding=0)


    def shift_y_scale(self, plot_idx, shift="up"):
        """
        Timed wrapper around manual Y-axis shifting.
        """
        start_time = perf_counter()

        try:
            return self._shift_y_scale_impl(
                plot_idx,
                shift=shift,
            )
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "shift_y_scale",
                elapsed,
                plot_idx=plot_idx,
                shift=shift,
            )


    def _shift_y_scale_impl(self, plot_idx, shift="up"):
        """
        Shifts the Y-axis center of the selected PlotWidget by moving it up or down.
        Shifts by moving Y range (shift="up"), or zooms out by expanding (shift="down").

        Parameters:
        - plot_idx: Index of the PlotWidget to adjust
        - shift: "up" to shift up (move center up), "down" to shift down (move center down)
        """
        self.disable_auto_y_for_plot(plot_idx)
        plt = self.waveform_plots[plot_idx]
        y_min, y_max = plt.viewRange()[1]
        span = (y_max - y_min) or 1.0
        center = (y_min + y_max) / 2
        shift_amount = span * 0.2  # 20% of current span

        if shift == "up":
            new_center = center + shift_amount
        elif shift == "down":
            new_center = center - shift_amount
        else:
            new_center = center

        new_min = new_center - span / 2
        new_max = new_center + span / 2
        plt.setYRange(new_min, new_max, padding=0)


    def update_auto_y_button_state(self, plot_idx, paused=False):
        """
        Update the visual state of one per-plot Auto-Y button.

        States:
        - AUTO ON: user wants Auto-Y and current X-window is small enough.
        - PAUSED: user wants Auto-Y but current X-window exceeds max_auto_y_window_sec.
        - OFF: user manually disabled Auto-Y.
        """
        if not hasattr(self, "auto_y_buttons"):
            return
        if plot_idx < 0 or plot_idx >= len(self.auto_y_buttons):
            return

        btn = self.auto_y_buttons[plot_idx]

        user_enabled = (
            hasattr(self, "auto_y_enabled_by_user")
            and plot_idx < len(self.auto_y_enabled_by_user)
            and self.auto_y_enabled_by_user[plot_idx]
        )

        if not user_enabled:
            btn.setText("OFF")
            btn.setToolTip("Manual Y-axis mode. Click to re-enable Auto-Y for this lead.")
            btn.setStyleSheet(
                "font-size: 8pt; color: #FFFFFF; background: #666666; "
                "min-width: 20px; min-height: 22px;"
            )
        elif paused:
            btn.setText("PAUSED")
            btn.setToolTip(
                "Auto-Y is paused because the visible time window is too large. "
                "Zoom in to resume."
            )
            btn.setStyleSheet(
                "font-size: 8pt; color: #FFFFFF; background: #B8860B; "
                "min-width: 20px; min-height: 22px;"
            )
        else:
            btn.setText("AUTO ON")
            btn.setToolTip("Automatically rescales this lead when the time window changes.")
            btn.setStyleSheet(
                "font-size: 8pt; color: #00274C; background: #FFCB05; "
                "min-width: 20px; min-height: 22px;"
            )


    def update_all_auto_y_button_states(self):
        """
        Update all Auto-Y buttons based on user preference and current X-window size.
        """
        if not hasattr(self, "waveform_plots") or not self.waveform_plots:
            return

        try:
            x_min, x_max = self.waveform_plots[0].viewRange()[0]
            visible_span = float(x_max) - float(x_min)
        except Exception:
            visible_span = 0.0

        max_window = getattr(self, "max_auto_y_window_sec", 300.0)
        paused = visible_span > max_window

        for i in range(len(getattr(self, "auto_y_buttons", []))):
            self.update_auto_y_button_state(i, paused=paused)


    def toggle_auto_y_for_plot(self, plot_idx):
        """
        Toggle per-plot Auto-Y.

        If Auto-Y is ON or PAUSED, clicking turns it OFF.
        If Auto-Y is OFF, clicking turns it ON and immediately attempts to autoscale
        that plot using the current visible X-window.
        """
        if not hasattr(self, "auto_y_enabled_by_user"):
            return
        if plot_idx < 0 or plot_idx >= len(self.auto_y_enabled_by_user):
            return

        currently_enabled = self.auto_y_enabled_by_user[plot_idx]

        if currently_enabled:
            # ON or PAUSED -> user manually turns it OFF.
            self.auto_y_enabled_by_user[plot_idx] = False
            self.update_all_auto_y_button_states()
        else:
            # OFF -> user turns it ON.
            self.auto_y_enabled_by_user[plot_idx] = True
            self.update_all_auto_y_button_states()

            # Immediately autoscale this plot if current X-window is allowed.
            self.autoscale_visible_y_for_plot(plot_idx, force=False)
            self.update_all_auto_y_button_states()


    def disable_auto_y_for_plot(self, plot_idx):
        """
        Disable Auto-Y for a plot after manual Y-axis intervention.
        """
        if not hasattr(self, "auto_y_enabled_by_user"):
            return
        if plot_idx < 0 or plot_idx >= len(self.auto_y_enabled_by_user):
            return

        self.auto_y_enabled_by_user[plot_idx] = False
        self.update_all_auto_y_button_states()


    def schedule_visible_y_autoscale(self, *args):
        """
        Debounce Auto-Y scaling after an X-axis view change.

        This prevents expensive autoscale computations from firing continuously
        while the user is rapidly scrolling or zooming.
        """
        if not hasattr(self, "auto_y_timer"):
            return

        debounce_ms = getattr(self, "auto_y_debounce_ms", 200)
        self.auto_y_timer.start(debounce_ms)


    def autoscale_visible_y_all(self):
        """
        Timed wrapper around visible-window Auto-Y calculations.
        """
        start_time = perf_counter()

        try:
            return self._autoscale_visible_y_all_impl()
        finally:
            elapsed = perf_counter() - start_time

            enabled_count = sum(
                1
                for enabled in getattr(
                    self,
                    "auto_y_enabled_by_user",
                    [],
                )
                if enabled
            )

            try:
                x_min, x_max = self.waveform_plots[0].viewRange()[0]
                visible_seconds = float(x_max) - float(x_min)
            except Exception:
                visible_seconds = "unknown"

            self._perf_log(
                "autoscale_visible_y_all",
                elapsed,
                enabled_plots=enabled_count,
                visible_seconds=visible_seconds,
            )


    def _autoscale_visible_y_all_impl(self):
        """
        Autoscale Y-axis for all plots whose Auto-Y is enabled by the user,
        using the current visible X-window plus a small time buffer.

        If the visible X-window is larger than max_auto_y_window_sec, Auto-Y is
        temporarily paused and no plots are autoscaled.
        """
        if not hasattr(self, "time_axis") or self.time_axis is None:
            return
        if not hasattr(self, "leads_ds") or self.leads_ds is None:
            return
        if not hasattr(self, "waveform_plots") or not self.waveform_plots:
            return

        try:
            x_min, x_max = self.waveform_plots[0].viewRange()[0]
            visible_span = float(x_max) - float(x_min)
        except Exception:
            return

        max_window = getattr(self, "max_auto_y_window_sec", 300.0)

        # If visible window is too large, show PAUSED for user-enabled plots.
        if visible_span > max_window:
            self.update_all_auto_y_button_states()
            return

        # Otherwise autoscale each plot that user has not manually turned off.
        for plot_idx in range(min(len(self.waveform_plots), len(self.leads_ds))):
            if (
                hasattr(self, "auto_y_enabled_by_user")
                and plot_idx < len(self.auto_y_enabled_by_user)
                and self.auto_y_enabled_by_user[plot_idx]
            ):
                self.autoscale_visible_y_for_plot(plot_idx, force=True)

        self.update_all_auto_y_button_states()

        
    def autoscale_visible_y_for_plot(self, plot_idx, force=False):
        """
        Autoscale one plot's Y-axis using the current visible X-window.

        Handles:
        - per-lead time axes
        - lower-rate signals stored with NaN placeholders
        - empty/all-NaN visible segments
        """
        if not hasattr(self, "leads_ds") or self.leads_ds is None:
            return False

        if not hasattr(self, "waveform_plots") or not self.waveform_plots:
            return False

        if plot_idx < 0 or plot_idx >= len(self.waveform_plots):
            return False

        if plot_idx >= len(self.leads_ds):
            return False

        sig = self.leads_ds[plot_idx]

        if sig is None:
            return False

        sig = np.asarray(sig, dtype=float)

        if sig.size == 0:
            return False

        # Use per-lead time axis if available.
        if (
            hasattr(self, "time_axes_by_lead")
            and self.time_axes_by_lead is not None
            and plot_idx < len(self.time_axes_by_lead)
            and self.time_axes_by_lead[plot_idx] is not None
            and len(self.time_axes_by_lead[plot_idx]) > 0
        ):
            time_axis = np.asarray(self.time_axes_by_lead[plot_idx], dtype=float)
        else:
            if not hasattr(self, "time_axis") or self.time_axis is None:
                return False
            time_axis = np.asarray(self.time_axis, dtype=float)

        if time_axis.size == 0:
            return False

        # Protect against length mismatch.
        n = min(time_axis.size, sig.size)

        if n <= 0:
            return False

        time_axis = time_axis[:n]
        sig = sig[:n]

        try:
            x_min, x_max = self.waveform_plots[0].viewRange()[0]
            x_min = float(x_min)
            x_max = float(x_max)
        except Exception:
            return False

        if not np.isfinite(x_min) or not np.isfinite(x_max) or x_max <= x_min:
            return False

        visible_span = x_max - x_min
        max_window = getattr(self, "max_auto_y_window_sec", 300.0)

        if visible_span > max_window:
            self.update_all_auto_y_button_states()
            return False

        buffer_sec = getattr(self, "auto_y_buffer_sec", 10.0)

        scale_start = x_min - buffer_sec
        scale_end = x_max + buffer_sec

        # For possibly nonuniform/per-lead time axis, use mask rather than only searchsorted.
        valid = (
            np.isfinite(time_axis)
            & np.isfinite(sig)
            & (time_axis >= scale_start)
            & (time_axis <= scale_end)
        )

        if not np.any(valid):
            return False

        segment = sig[valid]

        if segment.size < 2:
            return False

        try:
            y_lo, y_hi = np.nanpercentile(segment, [0.5, 99.5])
        except Exception:
            return False

        if not np.isfinite(y_lo) or not np.isfinite(y_hi):
            return False

        span = float(y_hi - y_lo)
        min_span = getattr(self, "auto_y_min_span", 0.25)
        margin_fraction = getattr(self, "auto_y_margin_fraction", 0.05)

        if span <= 0:
            center = float((y_hi + y_lo) / 2.0)
            y_min = center - min_span / 2.0
            y_max = center + min_span / 2.0
        else:
            margin = max(span * margin_fraction, min_span * margin_fraction)
            y_min = float(y_lo - margin)
            y_max = float(y_hi + margin)

        if not np.isfinite(y_min) or not np.isfinite(y_max) or y_max <= y_min:
            return False

        self.waveform_plots[plot_idx].setYRange(y_min, y_max, padding=0)
        return True

    # ------------------------------------------------------------------
    # Event Labels
    # ------------------------------------------------------------------

    def toggle_event_labels_visibility(self):
        """
        Show/hide all event marker text labels without replotting waveforms or lines.
        """
        self.event_labels_visible = not getattr(self, "event_labels_visible", True)

        self.set_event_labels_visible(self.event_labels_visible)

        if hasattr(self, "toggle_event_labels_btn"):
            if self.event_labels_visible:
                self.toggle_event_labels_btn.setText("Hide Event Labels")
            else:
                self.toggle_event_labels_btn.setText("Show Event Labels")


    def set_event_labels_visible(self, visible):
        """
        Set visibility for event marker TextItems only.
        Keeps vertical event lines visible.
        """
        if not hasattr(self, "waveform_plots"):
            return

        for plot in self.waveform_plots:
            for item in list(plot.items()):
                if isinstance(item, pg.TextItem) and getattr(item, "is_event_marker", False):
                    item.setVisible(visible)

    # ------------------------------------------------------------------
    # Waveform Finalization
    # ------------------------------------------------------------------
       
    def get_waveform_end_time(self):
        """
        Return final timestamp across all loaded signal time axes.
        """
        if hasattr(self, "loaded_waveform_end_sec") and self.loaded_waveform_end_sec is not None:
            return float(self.loaded_waveform_end_sec)

        global_start, global_end = self.get_loaded_global_time_range()

        if global_end is not None:
            return float(global_end)

        return None

    
    def is_at_waveform_end(self, value, tolerance=1e-6):
        """
        Check whether a timestamp is effectively at the final waveform point.

        Parameters
        ----------
        value : float
            Timestamp to check.
        tolerance : float
            Allowed floating-point tolerance.

        Returns
        -------
        bool
            True if value is at the waveform end.
        """
        waveform_end = self.get_waveform_end_time()
        if waveform_end is None or value is None:
            return False

        try:
            return abs(float(value) - waveform_end) <= tolerance
        except Exception:
            return False

    
    def last_annotation_reaches_waveform_end(self):
        """
        Check whether the most recent annotation ends at the final waveform point.

        Returns
        -------
        bool
            True if the last annotation reaches the end of the waveform.
        """
        annotations = getattr(self, "annotations", [])
        if not annotations:
            return False

        return self.is_at_waveform_end(annotations[-1].get("end", None))


    def clear_terminal_completion_fields(self):
        """
        Clear waveform completion state and terminal event metadata.
        """
        self.waveform_complete = False
        self.terminal_event_status = ""
        self.terminal_event_comment = ""

        for ann in getattr(self, "annotations", []):
            ann["waveform_complete"] = False
            ann["terminal_event_status"] = ""
            ann["terminal_event_comment"] = ""


    def apply_terminal_completion_to_annotations(self, status, comment):
        """
        Apply terminal completion metadata to the annotation list.

        The final decision is stored on the last annotation row. Earlier rows
        receive empty/default values so the saved CSV has consistent columns.

        Parameters
        ----------
        status : str
            Terminal event status.
        comment : str
            Final terminal event comment.
        """
        annotations = getattr(self, "annotations", [])

        for ann in annotations:
            ann["waveform_complete"] = False
            ann["terminal_event_status"] = ""
            ann["terminal_event_comment"] = ""

        if annotations:
            annotations[-1]["waveform_complete"] = True
            annotations[-1]["terminal_event_status"] = status
            annotations[-1]["terminal_event_comment"] = comment


    def update_finalize_button_state(self):
        """
        Enable the Finalize Waveform button only when the latest annotation
        reaches the final waveform point and the waveform is not already complete.
        """
        if not hasattr(self, "finalize_waveform_btn"):
            return

        can_finalize = (
            bool(getattr(self, "annotations", []))
            and self.last_annotation_reaches_waveform_end()
            and not getattr(self, "waveform_complete", False)
        )

        self.finalize_waveform_btn.setDisabled(not can_finalize)


    def show_final_completion_dialog(self):
        """
        Show a dialog asking whether the cardiac arrest/event continues beyond
        the available waveform.

        Returns
        -------
        tuple[str, str] or None
            Returns (status, comment) if accepted, otherwise None.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Finalize Waveform Annotation")

        layout = QVBoxLayout(dialog)

        instructions = QLabel(
            "The final annotation reaches the end of the waveform.\n\n"
            "Please indicate whether the cardiac arrest/event continues beyond "
            "the available waveform."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        radio_not_continue = QRadioButton(
            "Cardiac arrest/event does NOT continue beyond waveform"
        )
        radio_continues = QRadioButton(
            "Cardiac arrest/event CONTINUES beyond waveform"
        )

        layout.addWidget(radio_not_continue)
        layout.addWidget(radio_continues)

        comment_label = QLabel("Final comment:")
        layout.addWidget(comment_label)

        comment_box = QTextEdit()
        comment_box.setPlaceholderText(
            "Optional: Add final context or note for the last annotation..."
        )
        comment_box.setMinimumHeight(80)
        layout.addWidget(comment_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        result = {"accepted": False}

        def accept_if_valid():
            if not radio_not_continue.isChecked() and not radio_continues.isChecked():
                QMessageBox.warning(
                    dialog,
                    "Selection Required",
                    "Please select whether the cardiac arrest/event continues beyond the waveform.",
                )
                return

            result["accepted"] = True
            dialog.accept()

        buttons.accepted.connect(accept_if_valid)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec_() != QDialog.Accepted or not result["accepted"]:
            return None

        if radio_continues.isChecked():
            status = "continues_beyond_waveform"
        else:
            status = "does_not_continue_beyond_waveform"

        comment = comment_box.toPlainText().strip()

        return status, comment


    def handle_finalize_waveform_clicked(self):
        """
        Timed wrapper around finalization, redraw, saving, and UI updates.
        """
        start_time = perf_counter()

        try:
            return self._handle_finalize_waveform_clicked_impl()
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "handle_finalize_waveform_clicked TOTAL",
                elapsed,
                annotations=len(
                    getattr(self, "annotations", [])
                ),
                waveform_complete=getattr(
                    self,
                    "waveform_complete",
                    False,
                ),
            )
            

    def _handle_finalize_waveform_clicked_impl(self):
        """
        Finalize waveform annotation after the final annotation reaches the
        waveform end.

        This explicitly records whether the cardiac arrest/event continues beyond
        the available waveform, saves the file as COMPLETE, and deletes the
        redundant partial file.
        """
        if not self.last_annotation_reaches_waveform_end():
            self.mark_warning.setText(
                "Finalize is only available after the last annotation reaches the end of the waveform."
            )
            self.mark_warning.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#B71234;"
            )
            self.mark_warning.setWordWrap(True)
            self.update_finalize_button_state()
            return

        dialog_result = self.show_final_completion_dialog()
        if dialog_result is None:
            self.mark_warning.setText(
                "End of waveform reached. Finalize waveform when ready."
            )
            self.mark_warning.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#285680;"
            )
            self.mark_warning.setWordWrap(True)
            self.update_finalize_button_state()
            return

        status, comment = dialog_result

        self.waveform_complete = True
        self.terminal_event_status = status
        self.terminal_event_comment = comment

        self.apply_terminal_completion_to_annotations(status, comment)

        self.update_table_data()
        self.update_waveform_and_mark()

        # Save immediately with _COMPLETE naming.
        self.save_all_to_file()

        if status == "continues_beyond_waveform":
            msg = (
                "Waveform annotation complete! Cardiac arrest/event marked as "
                "continuing beyond available waveform."
            )
        else:
            msg = (
                "Waveform annotation complete! Cardiac arrest/event marked as "
                "not continuing beyond available waveform."
            )

        self.mark_warning.setText(msg)
        self.mark_warning.setStyleSheet(
            "font-size:13px; font-weight:bold; color:#199E40;"
        )
        self.mark_warning.setWordWrap(True)

        self.update_sidebar_ui()

    # ------------------------------------------------------------------
    # Plotting and Marking on Waveform
    # ------------------------------------------------------------------

    def get_plot_safe_view_y_range(self, plot):
            try:
                y_min, y_max = plot.viewRange()[1]
                y_min = float(y_min)
                y_max = float(y_max)

                if not np.isfinite(y_min) or not np.isfinite(y_max) or y_max <= y_min:
                    return -1.0, 1.0

                return y_min, y_max

            except Exception:
                return -1.0, 1.0


    def plot_event_markers(self):
        """
        Timed wrapper around event-line and event-label construction.
        """
        start_time = perf_counter()

        try:
            return self._plot_event_markers_impl()
        finally:
            elapsed = perf_counter() - start_time

            manifest_events = getattr(self, "manifest_events", None)

            try:
                event_count = len(manifest_events)
            except Exception:
                event_count = 0

            self._perf_log(
                "plot_event_markers",
                elapsed,
                event_rows=event_count,
                waveform_plots=len(
                    getattr(self, "waveform_plots", [])
                ),
            )


    def _plot_event_markers_impl(self):
        """
        Plots vertical dashed lines and labels for each event in self.manifest_events,
        using the front end's relative second axis.
        """

        # Remove any existing event markers and labels
        for plot in self.waveform_plots:
            # Remove old InfiniteLine markers
            items_to_remove = [item for item in plot.items() if isinstance(item, pg.InfiniteLine) and getattr(item, 'is_event_marker', False)]
            for item in items_to_remove:
                plot.removeItem(item)
            # Remove old TextItem labels referenced in self.event_labels
            if hasattr(self, "event_labels"):
                for label in self.event_labels:
                    plot.removeItem(label)

        # Reset the event_labels list to hold new label references
        self.event_labels = []

        # No events to plot?
        if not hasattr(self, 'manifest_events') or self.manifest_events is None:
            print("No event markers to plot: manifest_events is None")
            return

        # Only plot events visible in current window
        plot_x_min = self.time_axis[0]
        plot_x_max = self.time_axis[-1]
        # U-M dark green for line
        event_color = (0, 128, 0)
        event_pen   = pg.mkPen(event_color, width=5, style=QtCore.Qt.DashLine)
        for plot in self.waveform_plots:
            y_min, y_max = plot.viewRange()[1]
            label_y = y_max - 0.05 * (y_max - y_min)
            for idx, row in self.manifest_events.iterrows():
                event_name = str(row['FLO_MEAS_NAME'])
                event_value = str(row['FLOWSHEET_VALUE'])
                event_sec = row['event_sec']

                # Add vertical line marker
                vline = pg.InfiniteLine(pos=event_sec, angle=90, pen=event_pen)
                vline.is_event_marker = True
                plot.addItem(vline)

                # Add label
                label_text = event_name

                # Optional: include value too, but keep it compact
                # label_text = f"{event_name}: {event_value}"
                label_color = pg.mkColor(event_color)
                label = pg.TextItem(
                    label_text,
                    color=label_color,
                    anchor=(0, 0.5),
                    fill=pg.mkBrush(255, 255, 255, 210),
                    border=pg.mkPen(label_color, width=1),
                )
                label.is_event_marker = True
                label.setVisible(getattr(self, "event_labels_visible", True))

                font = QFont("Arial")
                font.setPointSize(8)
                font.setBold(True)
                label.setFont(font)

                y_min, y_max = plot.viewRange()[1]
                y_span = y_max - y_min if y_max != y_min else 1.0

                # Happy median: upper-middle, but not at the top edge
                label_y = y_max - 0.35 * y_span

                x_min, x_max = plot.viewRange()[0]
                x_span = x_max - x_min if x_max != x_min else 1.0
                label_x = event_sec + 0.003 * x_span

                label.setPos(label_x, label_y)
                label.setZValue(1000)

                plot.addItem(label, ignoreBounds=True)
                self.event_labels.append(label)

        
        # Put in the Code start and End as Red markers
        if self.code_start_sec is not None and self.code_stop_sec is not None:
            event_color = (128, 0, 0)
            event_pen   = pg.mkPen(event_color, width=5, style=QtCore.Qt.DashLine)
            for plot in self.waveform_plots:
                y_min, y_max = plot.viewRange()[1]
                label_y = y_max - 0.05 * (y_max - y_min)
                # Add vertical line marker
                # Start Marker
                vline = pg.InfiniteLine(pos=self.code_start_sec, angle=90, pen=event_pen)
                vline.is_event_marker = True
                plot.addItem(vline)
                # End Marker
                vline = pg.InfiniteLine(pos=self.code_stop_sec, angle=90, pen=event_pen)
                vline.is_event_marker = True
                plot.addItem(vline)

        # Put in the Recording start and End as Purple markers
        if self.recording_start_sec is not None and self.recording_end_sec is not None:
            event_color = (128, 128, 0)
            event_pen   = pg.mkPen(event_color, width=5, style=QtCore.Qt.DashLine)
            for plot in self.waveform_plots:
                y_min, y_max = self.get_plot_safe_view_y_range(plot)
                label_y = y_max - 0.05 * (y_max - y_min)
                # Add vertical line marker
                # Start Marker
                vline = pg.InfiniteLine(pos=self.recording_start_sec, angle=90, pen=event_pen)
                vline.is_event_marker = True
                plot.addItem(vline)
                # End Marker
                vline = pg.InfiniteLine(pos=self.recording_end_sec, angle=90, pen=event_pen)
                vline.is_event_marker = True
                plot.addItem(vline)


    def plot_all_leads(self):
        """
        Timed wrapper around waveform curve and event-marker construction.
        """
        start_time = perf_counter()

        try:
            return self._plot_all_leads_impl()
        finally:
            elapsed = perf_counter() - start_time

            total_points = 0

            for lead in getattr(self, "leads_ds", []) or []:
                if lead is not None:
                    try:
                        total_points += len(lead)
                    except Exception:
                        pass

            self._perf_log(
                "plot_all_leads",
                elapsed,
                total_lead_points=total_points,
                lead_count=len(getattr(self, "leads_ds", []) or []),
            )

            self._print_plot_performance_summary()


    def _plot_all_leads_impl(self):
        """
        Plots each lead waveform, applies robust autoscale (centered at zero), installs axis labels,
        and overlays event markers (vertical dashed lines + labels) for all valid events.
        Syncs X-range across all plots, with initial window set from self.win_size.
        Requires:
            - self.time_axis (array of timestamps)
            - self.leads_ds (waveform signals)
            - self.lead_names (lead labels)
            - self.manifest_events (pandas DataFrame of events, each with event_sec and FLO_MEAS_NAME)
            - self.code_start_sec, self.code_stop_sec (event filtering window, in epic seconds)
        """
        # ------------------------------------------------------------------
        # Clear, unlink, and reset all plots
        # ------------------------------------------------------------------
        for plot in self.waveform_plots:
            try:
                plot.setXLink(None)
            except Exception:
                pass

            plot.clear()
            plot.getViewBox().setMouseEnabled(x=True, y=False)

        if self.time_axis is None or len(self.time_axis) == 0:
            for plot in self.waveform_plots:
                plot.setTitle("No Data Loaded")
                plot.setYRange(-1.0, 1.0, padding=0)
            return

        # ------------------------------------------------------------------
        # Ensure arrays exist
        # ------------------------------------------------------------------
        time_axis = np.asarray(self.time_axis, dtype=float)

        leads = getattr(self, "leads_ds", [])
        lead_names = getattr(self, "lead_names", [])
        units = getattr(self, "units", [])
        time_axes_by_lead = getattr(self, "time_axes_by_lead", None)

        if leads is None:
            leads = []

        if lead_names is None:
            lead_names = []

        if units is None:
            units = []

        # ------------------------------------------------------------------
        # Determine global loaded x-range
        # ------------------------------------------------------------------
        global_x_min = getattr(self, "loaded_waveform_start_sec", None)
        global_x_max = getattr(self, "loaded_waveform_end_sec", None)

        if global_x_min is None or global_x_max is None:
            try:
                global_x_min, global_x_max = self.get_loaded_global_time_range()
            except Exception:
                global_x_min, global_x_max = None, None

        if global_x_min is None or global_x_max is None:
            finite_t = time_axis[np.isfinite(time_axis)]

            if finite_t.size == 0:
                for plot in self.waveform_plots:
                    plot.setTitle("No Valid Time Axis")
                    plot.setYRange(-1.0, 1.0, padding=0)
                return

            global_x_min = float(finite_t[0])
            global_x_max = float(finite_t[-1])

        global_x_min = float(global_x_min)
        global_x_max = float(global_x_max)

        if not np.isfinite(global_x_min) or not np.isfinite(global_x_max):
            global_x_min = 0.0
            global_x_max = 1.0

        if global_x_max <= global_x_min:
            global_x_max = global_x_min + 1.0

        # Axis labels show relative seconds from loaded segment start.
        t0 = global_x_min

        for plot in self.waveform_plots:
            plot.setAxisItems({"bottom": RelativeAxis(t0, orientation="bottom")})

        # ------------------------------------------------------------------
        # Plot each row
        # ------------------------------------------------------------------
        n_rows = min(len(self.waveform_plots), len(leads))

        for i in range(n_rows):
            plot = self.waveform_plots[i]
            sig = leads[i]

            name = lead_names[i] if i < len(lead_names) else f"Signal {i + 1}"
            unit = units[i] if i < len(units) else ""

            unit = "" if unit is None else str(unit)
            label_text = f"{name} ({unit})" if unit else str(name)

            plot.setLabel(
                "left",
                label_text,
                color=UM_BLUE,
                size="10pt",
            )

            # --------------------------------------------------------------
            # Get x-axis for this signal.
            # Critical: x is always assigned before use.
            # --------------------------------------------------------------
            if (
                time_axes_by_lead is not None
                and i < len(time_axes_by_lead)
                and time_axes_by_lead[i] is not None
                and len(time_axes_by_lead[i]) > 0
            ):
                x = np.asarray(time_axes_by_lead[i], dtype=float)
            else:
                x = np.asarray(time_axis, dtype=float)

            # --------------------------------------------------------------
            # Handle empty signal
            # --------------------------------------------------------------
            if sig is None or len(sig) == 0:
                plot.setTitle(f"{name} (no data)")
                plot.setXRange(global_x_min, global_x_max, padding=0)
                plot.setYRange(-1.0, 1.0, padding=0)

                if hasattr(self, "add_no_data_label"):
                    self.add_no_data_label(plot, f"{name}: No data")

                continue

            y = np.asarray(sig, dtype=float)

            # --------------------------------------------------------------
            # Protect against length mismatch
            # --------------------------------------------------------------
            n = min(len(x), len(y))

            if n <= 0:
                plot.setTitle(f"{name} (no data)")
                plot.setXRange(global_x_min, global_x_max, padding=0)
                plot.setYRange(-1.0, 1.0, padding=0)

                if hasattr(self, "add_no_data_label"):
                    self.add_no_data_label(plot, f"{name}: No data")

                continue

            x = x[:n]
            y = y[:n]

            finite_xy = np.isfinite(x) & np.isfinite(y)

            # --------------------------------------------------------------
            # All-NaN or no finite points
            # --------------------------------------------------------------
            if not np.any(finite_xy):
                plot.setTitle(f"{name} (no finite data)")
                plot.setXRange(global_x_min, global_x_max, padding=0)
                plot.setYRange(-1.0, 1.0, padding=0)

                if hasattr(self, "add_no_data_label"):
                    self.add_no_data_label(plot, f"{name}: No finite data")

                continue

            # --------------------------------------------------------------
            # Plot only finite samples.
            #
            # This is important for lower-rate signals stored on a higher-rate
            # shared time vector with NaN placeholders, e.g.:
            #
            #   [-22.8, nan, -23.8, nan, ...]
            #
            # We do NOT interpolate. We simply remove placeholder NaNs so the
            # true lower-rate samples are connected at their real timestamps.
            # --------------------------------------------------------------
            x_plot = x[finite_xy]
            y_plot = y[finite_xy]

            try:
                curve = plot.plot(
                    x_plot,
                    y_plot,
                    pen="b",
                    name=name,
                    # autoDownsample=True,
                    # clipToView=True,
                )
            except TypeError:
                curve = plot.plot(
                    x_plot,
                    y_plot,
                    pen="b",
                    name=name,
                )

            try:
                curve.setDownsampling(auto=True, method="peak")
            except Exception:
                pass

            try:
                curve.setClipToView(True)
            except Exception:
                pass

            plot.setTitle(str(name))

            # --------------------------------------------------------------
            # Safe y-scale
            # --------------------------------------------------------------
            if hasattr(self, "get_safe_y_range"):
                y_min, y_max, has_data = self.get_safe_y_range(y)
            else:
                finite_y = y[np.isfinite(y)]

                if finite_y.size == 0:
                    y_min, y_max, has_data = -1.0, 1.0, False
                else:
                    y_lo, y_hi = np.nanpercentile(finite_y, [0.5, 99.5])
                    half_span = max(abs(float(y_lo)), abs(float(y_hi)))
                    margin = 0.1 * half_span if half_span > 0 else 1.0
                    y_min = -half_span - margin
                    y_max = half_span + margin
                    has_data = (
                        np.isfinite(y_min)
                        and np.isfinite(y_max)
                        and y_max > y_min
                    )

            if has_data:
                plot.setYRange(y_min, y_max, padding=0)
            else:
                plot.setYRange(-1.0, 1.0, padding=0)

                if hasattr(self, "add_no_data_label"):
                    self.add_no_data_label(plot, f"{name}: No data")

        # ------------------------------------------------------------------
        # If there are more plot widgets than signals, mark extra rows empty
        # ------------------------------------------------------------------
        for i in range(n_rows, len(self.waveform_plots)):
            plot = self.waveform_plots[i]
            plot.setTitle("No signal assigned")
            plot.setXRange(global_x_min, global_x_max, padding=0)
            plot.setYRange(-1.0, 1.0, padding=0)

            if hasattr(self, "add_no_data_label"):
                self.add_no_data_label(plot, "No signal assigned")

        # ------------------------------------------------------------------
        # Initial X range
        # ------------------------------------------------------------------
        winlen = float(self.win_size.value()) if hasattr(self, "win_size") else 10.0

        left = global_x_min
        right = min(global_x_max, left + winlen)

        if right <= left:
            right = left + 1.0

        self.waveform_plots[0].setXRange(left, right, padding=0)

        for plot in self.waveform_plots[1:]:
            plot.setXLink(self.waveform_plots[0])

        # ------------------------------------------------------------------
        # Restrict interaction to X only
        # ------------------------------------------------------------------
        for plot in self.waveform_plots:
            plot.getViewBox().setMouseEnabled(x=True, y=False)

        # ------------------------------------------------------------------
        # Plot manifest/event markers after y-ranges are valid
        # ------------------------------------------------------------------
        if hasattr(self, "manifest_events") and self.manifest_events is not None:
            if not self.manifest_events.empty:
                self.plot_event_markers()

    # ------------------------------------------------------------------
    # Annotation Functionality
    # ------------------------------------------------------------------

    def delete_annotation_files_for_current_user(self):
        """
        Delete both partial and COMPLETE annotation files for current user/selected waveform.
        """
        output_folder = self.get_annotation_output_folder()
        if not output_folder:
            return

        partial_filename, complete_filename = self.get_annotation_filenames()

        partial_path = os.path.join(output_folder, partial_filename)
        complete_path = os.path.join(output_folder, complete_filename)

        for path in [partial_path, complete_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"Deleted annotation file: {path}")
                except Exception as e:
                    print(f"Warning: Could not delete annotation file {path}: {e}")

        self.refresh_selected_record_annotation_status()


    def handle_remove_last_mark(self):
        """
        Timed wrapper around undo, graphics rebuilding, saving, and refresh.
        """
        annotation_count_before = len(
            getattr(self, "annotations", [])
        )

        start_time = perf_counter()

        try:
            return self._handle_remove_last_mark_impl()
        finally:
            elapsed = perf_counter() - start_time

            annotation_count_after = len(
                getattr(self, "annotations", [])
            )

            self._perf_log(
                "handle_remove_last_mark TOTAL",
                elapsed,
                annotations_before=annotation_count_before,
                annotations_after=annotation_count_after,
            )


    def _handle_remove_last_mark_impl(self):
        """
        Removes the most recent annotation ('last mark') from table and plots.
        Resets sidebar and markers to previous state or initial if no marks remain.
        """
        if not self.annotations:
            return

        removed_ann = self.annotations.pop()
        print(f"Removed last annotation: {removed_ann}")

        # If removing after completion, clear terminal completion state.
        self.clear_terminal_completion_fields()
        self.mark_warning.setText("")

        if self.annotations:
            self.last_mark = self.annotations[-1]["end"]
        else:
            self.last_mark = None
            self.current_marker = None

        self.current_marker = None

        self.update_table_data()
        self.update_waveform_and_mark()
        self.update_sidebar_ui()
        self.update_finalize_button_state()

        # Keep files synced after undo.
        if self.annotations:
            self.save_all_to_file()
        else:
            self.delete_annotation_files_for_current_user()


    def handle_load_annotation(self):
        """
        Timed wrapper around annotation file loading and graphics reconstruction.
        """
        start_time = perf_counter()

        try:
            return self._handle_load_annotation_impl()
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "handle_load_annotation TOTAL",
                elapsed,
                annotations=len(
                    getattr(self, "annotations", [])
                ),
                waveform_complete=getattr(
                    self,
                    "waveform_complete",
                    False,
                ),
            )


    def _handle_load_annotation_impl(self):
        print("LOAD ANNOTATIONS BUTTON CLICKED")
        user_name = self.get_user_name()
        subject = self.get_selected_subject_name()

        # --- Username check ---
        if not user_name:
            self.mark_warning.setText("Please select your User Name before loading annotations.")
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        if not subject:
            self.mark_warning.setText("Please select a subject before loading annotations.")
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        # --- Build the annotation file path ---
        output_folder = self.get_annotation_output_folder()

        if not output_folder:
            self.mark_warning.setText("Could not determine annotation output folder.")
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        partial_filename, complete_filename = self.get_annotation_filenames()

        partial_path = os.path.join(output_folder, partial_filename)
        complete_path = os.path.join(output_folder, complete_filename)

        if os.path.exists(complete_path):
            fullpath = complete_path
            loaded_complete_file = True
        elif os.path.exists(partial_path):
            fullpath = partial_path
            loaded_complete_file = False
        else:
            self.mark_warning.setText(
                f"No previous annotations found for '{user_name}' and subject '{subject}'."
            )
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        # --- Load the annotation file ---
        try:
            df = pd.read_csv(fullpath)
            self.annotations = df.to_dict(orient="records")
        except Exception as e:
            self.mark_warning.setText(f"Failed to load annotations: {e}")
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        # --- Normalize expected columns for old/partial files ---
        for ann in self.annotations:
            ann.setdefault("waveform_complete", False)
            ann.setdefault("terminal_event_status", "")
            ann.setdefault("terminal_event_comment", "")

            # Ensure start/end are numeric after CSV load
            try:
                ann["start"] = float(ann["start"])
            except Exception:
                pass

            try:
                ann["end"] = float(ann["end"])
            except Exception:
                pass

        # --- Restore completion state ---
        self.waveform_complete = loaded_complete_file
        self.terminal_event_status = ""
        self.terminal_event_comment = ""

        if self.annotations and loaded_complete_file:
            last_ann = self.annotations[-1]
            self.terminal_event_status = str(last_ann.get("terminal_event_status", "") or "")
            self.terminal_event_comment = str(last_ann.get("terminal_event_comment", "") or "")

            # Make sure loaded complete file has completion metadata on final row
            last_ann["waveform_complete"] = True

        elif self.annotations:
            # Partial/in-progress file
            self.waveform_complete = False
            self.terminal_event_status = ""
            self.terminal_event_comment = ""

            # Ensure partial file rows are not marked complete
            for ann in self.annotations:
                ann["waveform_complete"] = False
                ann["terminal_event_status"] = ""
                ann["terminal_event_comment"] = ""

        else:
            self.waveform_complete = False
            self.terminal_event_status = ""
            self.terminal_event_comment = ""

        # --- Set marker state for continued marking ---
        if self.annotations:
            self.last_mark = float(self.annotations[-1]["end"])
            self.current_marker = None
        else:
            self.last_mark = None
            self.current_marker = None

        # --- Sync table and plots to match loaded annotations ---
        self.update_table_data()
        self.update_waveform_and_mark()
        self.update_sidebar_ui()
        self.update_finalize_button_state()
        # self.refresh_subject_dropdown_preserve_selection()

        # --- Center plot(s) on last annotation's end if loaded ---
        if self.annotations and hasattr(self, "time_axis") and self.time_axis is not None and len(self.time_axis) > 0:
            last_mark_end = float(self.annotations[-1]["end"])
            winlen = float(self.win_size.value()) if hasattr(self, "win_size") else 10.0

            left = max(last_mark_end - winlen / 2.0, float(self.time_axis[0]))
            right = left + winlen

            # Prevent right side from extending past waveform end if possible
            waveform_end = float(self.time_axis[-1])
            if right > waveform_end:
                right = waveform_end
                left = max(float(self.time_axis[0]), right - winlen)

            self.waveform_plots[0].setXRange(left, right, padding=0)
            for plt in self.waveform_plots[1:]:
                plt.setXLink(self.waveform_plots[0])

        # --- Show annotation session resume/completion message and file modification date ---
        if self.waveform_complete:
            if self.terminal_event_status == "continues_beyond_waveform":
                resume_msg = (
                    f"Loaded COMPLETE annotation session for '{user_name}' on '{subject}'.\n"
                    f"Cardiac arrest/event continues beyond waveform."
                )
            elif self.terminal_event_status == "does_not_continue_beyond_waveform":
                resume_msg = (
                    f"Loaded COMPLETE annotation session for '{user_name}' on '{subject}'.\n"
                    f"Cardiac arrest/event does not continue beyond waveform."
                )
            else:
                resume_msg = (
                    f"Loaded COMPLETE annotation session for '{user_name}' on '{subject}'."
                )
        else:
            resume_msg = f"Resuming annotation session for '{user_name}' on '{subject}'."

        try:
            mod_time = os.path.getmtime(fullpath)
            import datetime
            dt_str = datetime.datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")
            resume_msg = f"{resume_msg}\nLast saved: {dt_str}"
        except Exception:
            pass

        self.mark_warning.setText(resume_msg)
        self.mark_warning.setWordWrap(True)

        if self.waveform_complete:
            self.mark_warning.setStyleSheet(
                "color: #199E40; font-size: 13px; font-weight: bold;"
            )
        else:
            self.mark_warning.setStyleSheet(
                "color: #285680; font-size: 13px; font-weight: bold;"
            )

        # Make sure final visual state is correct after message override
        self.update_finalize_button_state()


    def get_loaded_global_time_range(self):
        """
        Return global min/max absolute epoch seconds across all loaded signal time axes.
        """
        starts = []
        stops = []

        if hasattr(self, "time_axes_by_lead") and self.time_axes_by_lead is not None:
            for t in self.time_axes_by_lead:
                if t is None:
                    continue

                arr = np.asarray(t, dtype=float)
                finite = arr[np.isfinite(arr)]

                if finite.size > 0:
                    starts.append(float(finite[0]))
                    stops.append(float(finite[-1]))

        elif hasattr(self, "time_axis") and self.time_axis is not None:
            arr = np.asarray(self.time_axis, dtype=float)
            finite = arr[np.isfinite(arr)]

            if finite.size > 0:
                starts.append(float(finite[0]))
                stops.append(float(finite[-1]))

        if not starts or not stops:
            return None, None

        return min(starts), max(stops)

    # ------------------------------------------------------------------
    # Loading Waveform Data
    # ------------------------------------------------------------------

    def load_subject_data(self):
        """
        Timed wrapper around the full subject-loading workflow.
        """
        start_time = perf_counter()

        try:
            return self._load_subject_data_impl()
        finally:
            elapsed = perf_counter() - start_time

            record = self.get_selected_subject_record() or {}

            self._perf_log(
                "load_subject_data TOTAL",
                elapsed,
                subject=record.get("subject", ""),
                encounter=record.get("encounter", ""),
                file_tag=record.get("file_tag", ""),
                kind=record.get("kind", ""),
            )

            self._print_waveform_memory_summary()
            self._print_plot_performance_summary()

            
    def _load_subject_data_impl(self):
        subject_idx = self.subject_dropdown.currentIndex()
        if subject_idx < 0:
            print("No subject selected.")
            return

        record = self.subject_dropdown.currentData()
        base_folder = getattr(self, "base_folder", None)

        if not isinstance(record, dict):
            print("Invalid subject selection. Expected subject record dict.")
            self.data_store = {}
            return

        subject_name = record.get("subject", "")
        encounter_name = record.get("encounter", "")
        h5_path = record.get("h5_path", "")

        print(f"Button clicked: load subject {subject_name} from {base_folder}")
        print(f"Selected record: {record}")

        if not subject_name or not base_folder or not os.path.isdir(base_folder):
            print("No data loaded.")
            self.data_store = {}
            return

        # Store selected record for annotation save/load paths
        self.current_subject_record = record
        self.current_subject = subject_name
        self.current_encounter = encounter_name
        self.current_namespace = record.get("namespace", "")
        self.current_file_tag = record.get("file_tag", "")
        self.current_output_path = record.get("output_path", "")
        self.current_h5_path = h5_path
        # ------------------------------------------------------------------
        # IMPORTANT:
        # Always use timestamps from the waveform file itself.
        #
        # Do NOT use waveform_manifest.csv to crop/window the waveform.
        # The manifest is metadata only.
        # ------------------------------------------------------------------
        code_csv_path = os.path.join(base_folder, "waveform_manifest.csv")

        self.recording_start_sec = None
        self.recording_end_sec = None
        code_start_sec = None
        code_stop_sec = None

        waveform_load_start = perf_counter()

        loaded_waveforms = load_waveforms_for_subject(
            base_folder,
            record,
            recording_start_sec=None,
            code_start_sec=None,
            code_stop_sec=None,
            desired_waveforms=WAVEFORM_PLOT_ORDER,
        )

        waveform_load_elapsed = perf_counter() - waveform_load_start

        # Timing Waveform Loading
        self._perf_log(
            "load_waveforms_for_subject",
            waveform_load_elapsed,
            kind=record.get("kind", ""),
            source_path=record.get(
                "h5_path",
                record.get("csv_path", ""),
            ),
        )
        # Start timer
        normalization_start = perf_counter()

        times_ds = loaded_waveforms.get("times_ds", None)
        times_by_lead = loaded_waveforms.get("times_by_lead", None)
        leads_ds = loaded_waveforms.get("leads_ds", None)
        lead_names = loaded_waveforms.get("lead_names", None)
        units = loaded_waveforms.get("units", None)
        Fs = loaded_waveforms.get("Fs", None)

        # Calculate Time
        normalization_elapsed = perf_counter() - normalization_start
        self._perf_log(
            "normalize_and_assign_loaded_waveforms",
            normalization_elapsed,
            global_time_points=len(times_ds),
            lead_count=len(leads_ds),
        )

        if times_ds is None:
            times_ds = np.array([])

        times_ds = np.asarray(times_ds, dtype=float)

        if leads_ds is None:
            leads_ds = []

        if lead_names is None:
            lead_names = []

        if units is None:
            units = []

        if times_by_lead is None:
            times_by_lead = [
                times_ds for _ in leads_ds
            ]
        else:
            times_by_lead = [
                np.asarray(t, dtype=float) if t is not None else np.array([])
                for t in times_by_lead
            ]

        self.time_axis = times_ds
        self.time_axes_by_lead = times_by_lead
        self.leads_ds = leads_ds
        self.lead_names = lead_names
        self.units = units
        self.Fs = Fs
        if times_ds is None:
            times_ds = np.array([])

        times_ds = np.asarray(times_ds, dtype=float)

        global_start, global_end = self.get_loaded_global_time_range()

        self.loaded_waveform_start_sec = global_start
        self.loaded_waveform_end_sec = global_end

        self.recording_start_sec = global_start
        self.recording_end_sec = global_end

        if global_start is not None:
            self.last_mark = float(global_start)
        else:
            self.last_mark = 0.0

        # These should not come from the manifest anymore.
        self.code_start_sec = None
        self.code_stop_sec = None

        print(times_ds, leads_ds, lead_names, units, Fs)

        # --- Filter manifest events for current subject and code window ---
        # ------------------------------------------------------------------
        # Load manifest events as optional metadata only.
        # Do not use them to crop the waveform.
        # Do not set code_start_sec/code_stop_sec from them.
        # ------------------------------------------------------------------

        # Timer for Manifest Loader
        manifest_load_start = perf_counter()

        self.manifest_events = pd.DataFrame()

        if os.path.exists(code_csv_path):
            try:
                manifest_events_df = get_events_for_window(
                    code_csv_path,
                    subject_name,
                    window_start=0,
                    window_end=float("inf"),
                )

                if "event_sec" not in manifest_events_df.columns and "RECORDED_TIME" in manifest_events_df.columns:
                    manifest_events_df["event_sec"] = manifest_events_df["RECORDED_TIME"].apply(
                        datetime_string_to_seconds_since_1970
                    )

                if {"FLO_MEAS_NAME", "FLOWSHEET_VALUE", "RECORDED_TIME"}.issubset(manifest_events_df.columns):
                    manifest_events_df = manifest_events_df.drop_duplicates(
                        subset=["FLO_MEAS_NAME", "FLOWSHEET_VALUE", "RECORDED_TIME"]
                    )

                # Optional: keep only events that fall inside the loaded waveform file.
                if len(times_ds) > 0 and "event_sec" in manifest_events_df.columns:
                    t_start = float(self.loaded_waveform_start_sec)
                    t_stop = float(self.loaded_waveform_end_sec)

                    manifest_events_df = manifest_events_df[
                        (manifest_events_df["event_sec"] >= t_start)
                        &
                        (manifest_events_df["event_sec"] <= t_stop)
                    ].copy()

                self.manifest_events = manifest_events_df

                print("Loaded manifest metadata/events:")
                print(self.manifest_events)

            except Exception as e:
                print(f"WARNING: Could not load manifest metadata/events: {e}")
                self.manifest_events = pd.DataFrame()
        else:
            print(f"WARNING: waveform_manifest.csv not found at {code_csv_path}")
            self.manifest_events = pd.DataFrame()

        # Manifest Timer stop
        manifest_load_elapsed = perf_counter() - manifest_load_start

        self._perf_log(
            "load_manifest_events",
            manifest_load_elapsed,
            event_count=len(self.manifest_events),
            manifest_path=code_csv_path,
        )

        print("data x:", times_ds[:10], "...", times_ds[-10:])
        print("annot", [ (a['start'], a['end']) for a in self.annotations ])
        print("viewRange before region:", self.waveform_plots[0].viewRange())

        self.time_axis = times_ds          
        self.leads_ds = leads_ds            
        self.lead_names = lead_names
        self.units = units
        self.Fs = Fs

        # Reset Auto-Y state for newly loaded subject.
        self.auto_y_enabled_by_user = [True for _ in self.waveform_plots]
        self.update_all_auto_y_button_states()

        if len(self.time_axis) > 0:
            self.last_mark = float(self.time_axis[0])
        else:
            self.last_mark = 0.0
        self.current_marker = None
    
        data_store_start = perf_counter()

        self.data_store = {
            "time": times_ds.tolist() if hasattr(times_ds, "tolist") else list(times_ds),
            "leads": [
                lead.tolist() if lead is not None else None
                for lead in leads_ds
            ],
            "lead_names": lead_names,
            "subject": subject_name,
            "encounter": encounter_name,
            "file_tag": record.get("file_tag", ""),
            "source_path": record.get(
                "h5_path",
                record.get("csv_path", ""),
            ),
        }

        data_store_elapsed = perf_counter() - data_store_start

        stored_lead_value_count = sum(
            len(lead)
            for lead in self.data_store["leads"]
            if isinstance(lead, list)
        )

        self._perf_log(
            "build_data_store_python_lists",
            data_store_elapsed,
            time_values=len(self.data_store["time"]),
            lead_values=stored_lead_value_count,
        )
        self.annotations = []
        print("Loaded data for:", subject_name)
        # After assigning self.time_axis, self.leads_ds, self.lead_names:
        # --- Pass code bounds, events to the plotting function ---
        self.code_start_sec = code_start_sec
        self.code_stop_sec  = code_stop_sec

        # Set waveform complete flag to False for new subject load, which controls whether marking is allowed
        self.waveform_complete = False

        if not hasattr(self, "event_labels_visible"):
            self.event_labels_visible = True
        
        self.plot_all_leads()

        self.schedule_visible_y_autoscale()

        self.update_waveform_and_mark()
        self.update_table_data()


    def update_sidebar_ui(self):
        # --- Clear sidebar after marking ---
        if getattr(self, "pending_clear_sidebar", False):
            self.pending_clear_sidebar = False

            # Reset CPR buttons
            self.cpr_group.setExclusive(False)
            self.cpr_yes.setChecked(False)
            self.cpr_no.setChecked(False)
            self.cpr_U2D.setChecked(False)
            self.cpr_group.setExclusive(True)
            self.cpr_yes.setDisabled(False)
            self.cpr_no.setDisabled(False)
            self.cpr_U2D.setDisabled(False)

            # Reset Rhythm dropdown
            self.rhythm_dropdown.blockSignals(True)
            self.rhythm_dropdown.setCurrentIndex(-1)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_dropdown.blockSignals(False)

            # Visual: Rhythm label as strikethrough + gray
            if hasattr(self, "rhythm_label"):
                self.rhythm_label.setText("<span style='text-decoration:line-through; color:#888;'>Rhythm Type</span>")
                self.rhythm_label.setStyleSheet("font-size:13px;")

            # Reset Explanation comment
            self.rhythm_explanation.blockSignals(True)
            self.rhythm_explanation.setPlainText("")
            self.rhythm_explanation.setDisabled(True)
            self.rhythm_explanation.blockSignals(False)

            # Reset Mark warning/button
            self.mark_warning.setText("")
            self.mark_btn.setDisabled(True)
            return

        if getattr(self, "waveform_complete", False):
            self.mark_btn.setDisabled(True)

            self.cpr_yes.setDisabled(True)
            self.cpr_no.setDisabled(True)
            self.cpr_U2D.setDisabled(True)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_explanation.setDisabled(True)

            if hasattr(self, "finalize_waveform_btn"):
                self.finalize_waveform_btn.setDisabled(True)

            if getattr(self, "terminal_event_status", "") == "continues_beyond_waveform":
                msg = (
                    "Waveform annotation complete! Cardiac arrest/event continues "
                    "beyond available waveform."
                )
            else:
                msg = (
                    "Waveform annotation complete! No further marking needed."
                )

            self.mark_warning.setText(msg)
            self.mark_warning.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#199E40;"
            )
            self.mark_warning.setWordWrap(True)

            self.remove_last_btn.setDisabled(len(self.annotations) == 0)
            return

        # If we are no longer complete, make annotation controls usable again.
        self.cpr_yes.setDisabled(False)
        self.cpr_no.setDisabled(False)
        self.cpr_U2D.setDisabled(False)

        # --- Main logic ---
        cpr      = self.get_cpr_val()
        rhythm   = self.rhythm_dropdown.currentText() if self.rhythm_dropdown.isEnabled() else ""
        rex      = self.rhythm_explanation.toPlainText()
        user_name = self.username_input.currentText()
        marker    = self.current_marker
        last_mark = self.last_mark

        # --- CPR and Rhythm section UI logic + visual Rhythm label ---
        if cpr == "Yes":
            # Disable rhythm dropdown & visually indicate as disabled
            self.rhythm_dropdown.blockSignals(True)
            self.rhythm_dropdown.setCurrentIndex(-1)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_dropdown.blockSignals(False)
            if hasattr(self, "rhythm_label"):
                self.rhythm_label.setText("<span style='text-decoration:line-through; color:#888;'>Rhythm Type</span>")
                self.rhythm_label.setStyleSheet("font-size:13px;")
            # Disable explanation/comment
            self.rhythm_explanation.blockSignals(True)
            self.rhythm_explanation.setPlainText("")
            self.rhythm_explanation.setDisabled(True)
            self.rhythm_explanation.blockSignals(False)

        elif cpr == "Unable to Determine":
            # Disable rhythm dropdown & visually indicate as disabled
            self.rhythm_dropdown.blockSignals(True)
            self.rhythm_dropdown.setCurrentIndex(-1)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_dropdown.blockSignals(False)
            if hasattr(self, "rhythm_label"):
                self.rhythm_label.setText("<span style='text-decoration:line-through; color:#888;'>Rhythm Type</span>")
                self.rhythm_label.setStyleSheet("font-size:13px;")
            # Enable explanation/comment
            self.rhythm_explanation.setDisabled(False)

        elif cpr == "No":
            # Enable rhythm dropdown & visually restore label
            self.rhythm_dropdown.setDisabled(False)
            self.rhythm_dropdown.blockSignals(False)

            if hasattr(self, "rhythm_label"):
                self.rhythm_label.setText("Rhythm Type")
                self.rhythm_label.setStyleSheet("font-size:13px; color: #00274C;")

            rhythm = self.rhythm_dropdown.currentText()

            # Explanation is required/editable only for these rhythm labels
            if rhythm in ["Unable to Determine", "Other"]:
                self.rhythm_explanation.setDisabled(False)
            else:
                self.rhythm_explanation.blockSignals(True)
                self.rhythm_explanation.setPlainText("")
                self.rhythm_explanation.setDisabled(True)
                self.rhythm_explanation.blockSignals(False)
        else:
            # No CPR selection yet; everything disabled, visually gray
            self.rhythm_dropdown.blockSignals(True)
            self.rhythm_dropdown.setCurrentIndex(-1)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_dropdown.blockSignals(False)
            if hasattr(self, "rhythm_label"):
                self.rhythm_label.setText("<span style='text-decoration:line-through; color:#888;'>Rhythm Type</span>")
                self.rhythm_label.setStyleSheet("font-size:13px;")
            self.rhythm_explanation.blockSignals(True)
            self.rhythm_explanation.setPlainText("")
            self.rhythm_explanation.setDisabled(True)
            self.rhythm_explanation.blockSignals(False)

        # --- Warnings & mark button logic ---
        warnings = []

        # --- Plot marker requirements ---
        if marker is None:
            warnings.append("Click on the plot to place a marker before marking.")
        elif last_mark is None:
            warnings.append("No previous mark set.")
        else:
            try:
                interval = float(marker) - float(last_mark)
            except Exception:
                warnings.append("Error calculating marked interval.")
            else:
                if interval <= 0 or interval < 1.0:
                    warnings.append("Marked interval must be at least 1 second.")

        # --- Required annotation fields ---
        if not warnings:
            if not user_name or not user_name.strip():
                warnings.append("Select your User Name before marking.")
            if not cpr:
                warnings.append("Select the CPR question before marking.")

            if cpr == "No":
                if not rhythm or rhythm == "":
                    warnings.append("Select a Rhythm Label before marking.")
                elif rhythm in ["Unable to Determine", "Other"] and (not rex or not rex.strip()):
                    warnings.append("Explanation required for selected rhythm.")
            elif cpr == "Unable to Determine":
                if not rex or not rex.strip():
                    warnings.append("Explanation required for 'Unable to Determine' CPR answer.")

        # --- Display warnings and enable/disable mark button ---
        warning_msg = "\n".join(warnings)
        self.mark_warning.setText(warning_msg)
        self.mark_warning.setWordWrap(True)
        self.mark_btn.setDisabled(bool(warnings))
        self.remove_last_btn.setDisabled(len(self.annotations) == 0)

        self.update_finalize_button_state()

        # Check completed annotation
        if getattr(self, "waveform_complete", False):
            self.mark_btn.setDisabled(True)
            self.mark_warning.setText("Waveform annotation complete! No further marking needed.")
            self.mark_warning.setStyleSheet("font-size:13px; font-weight:bold; color:#199E40;")
            # Disable other annotation fields if desired
            return


    def make_plot_click_handler(self, lead_idx):
        def handler(mouse_event):
            if mouse_event.button() != Qt.LeftButton:
                return

            if getattr(self, "waveform_complete", False):
                self.mark_warning.setText(
                    "Waveform annotation is complete. Remove the last mark if you need to revise it."
                )
                self.mark_warning.setStyleSheet(
                    "font-size:13px; font-weight:bold; color:#199E40;"
                )
                self.mark_warning.setWordWrap(True)
                return

            vb = self.waveform_plots[lead_idx].getViewBox()
            mouse_point = vb.mapSceneToView(mouse_event.scenePos())
            t_clicked = float(mouse_point.x())

            waveform_end = self.get_waveform_end_time()
            if waveform_end is not None:
                # Do not allow marking beyond waveform.
                # If within <= 1 second of end, snap to final point.
                if t_clicked > waveform_end:
                    t_clicked = waveform_end
                elif (waveform_end - t_clicked) <= 1.0:
                    t_clicked = waveform_end

            if self.last_mark is None:
                self.last_mark = t_clicked
                self.current_marker = None
                print(f"Initialized last_mark={self.last_mark:.2f}")
                self.update_sidebar_ui()
                self.update_waveform_and_mark()
            elif t_clicked > self.last_mark:
                self.current_marker = t_clicked
                print(f"Set region: last_mark={self.last_mark:.2f}, marker={self.current_marker:.2f}")
                self.update_sidebar_ui()
                self.update_waveform_and_mark()
            else:
                print(f"Ignored click at {t_clicked:.2f} (must be after last_mark={self.last_mark:.2f})")

        return handler


    def handle_x_scrollbar(self, value):
        window_width = self.win_size.value()
        x_min = value
        x_max = x_min + window_width
        for plt in self.waveform_plots:
            plt.setXRange(x_min, x_max, padding=0)


    def handle_mark_clicked(self):
        """
        Timed wrapper around the complete Mark-button workflow.
        """
        annotation_count_before = len(
            getattr(self, "annotations", [])
        )

        start_time = perf_counter()

        try:
            return self._handle_mark_clicked_impl()
        finally:
            elapsed = perf_counter() - start_time

            annotation_count_after = len(
                getattr(self, "annotations", [])
            )

            self._perf_log(
                "handle_mark_clicked TOTAL",
                elapsed,
                annotations_before=annotation_count_before,
                annotations_after=annotation_count_after,
            )
            

    def _handle_mark_clicked_impl(self):
        print("handle_mark_clicked CALLED")

        if getattr(self, "waveform_complete", False):
            self.mark_warning.setText(
                "Waveform annotation is already complete. Remove the last mark to revise."
            )
            self.mark_warning.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#199E40;"
            )
            self.mark_warning.setWordWrap(True)
            return

        final_segment_reached = False

        if (
            self.current_marker is not None
            and self.last_mark is not None
            and self.current_marker > self.last_mark
        ):
            record = self.get_selected_subject_record()
            subject_name = self.get_selected_subject_name()

            ann = {
                "user": self.get_user_name(),
                "subject": subject_name,
                "encounter": record.get("encounter", "") if record else "",
                "namespace": record.get("namespace", "") if record else "",
                "file_tag": record.get("file_tag", "") if record else "",
                "source_path": (
                    record.get(
                        "h5_path",
                        record.get("csv_path", ""),
                    )
                    if record
                    else ""
                ),
                "cpr": self.get_cpr_val(),
                "rhythm_label": (
                    self.rhythm_dropdown.currentText()
                    if self.rhythm_dropdown.isEnabled()
                    else ""
                ),
                "rhythm_expl": self.rhythm_explanation.toPlainText(),
                "start": self.last_mark,
                "end": self.current_marker,
                "waveform_complete": False,
                "terminal_event_status": "",
                "terminal_event_comment": "",
            }

            final_segment_reached = self.is_at_waveform_end(ann["end"])

            print(f"APPENDING ANNOTATION: {ann}")
            self.annotations.append(ann)

            # Prepare for the next annotation.
            self.last_mark = self.current_marker
            self.current_marker = None
            self.pending_clear_sidebar = True
            self.update_sidebar_ui()
        else:
            print("Attempted to mark invalid or zero-length region.")

        self.update_sidebar_ui()
        self.update_waveform_and_mark()
        self.update_table_data()
        self.update_finalize_button_state()

        if final_segment_reached and not getattr(
            self,
            "waveform_complete",
            False,
        ):
            self.mark_warning.setText(
                "End of waveform reached. Please click "
                "'Finalize Waveform' when ready."
            )
            self.mark_warning.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#285680;"
            )
            self.mark_warning.setWordWrap(True)
            self.update_finalize_button_state()

        # Do not autosave after every mark.
        # The QTimer performs autosave every two minutes.

        print(
            "Current ANNOTATIONS LIST after marking:",
            self.annotations,
        )


    def get_user_name(self):
        """
        Return the selected username from the username widget.

        Supports both QComboBox and QLineEdit.
        """
        if hasattr(self.username_input, "currentText"):
            return self.username_input.currentText().strip()
        elif hasattr(self.username_input, "text"):
            return self.username_input.text().strip()
        return ""
    
    def get_selected_subject_record(self):
        """
        Return the selected subject/waveform record from the subject dropdown.

        With the new H5 loader, currentData() should be a dict returned by
        processing.list_subjects().
        """
        record = self.subject_dropdown.currentData()
        return record if isinstance(record, dict) else None


    def get_selected_subject_name(self):
        """
        Return the selected subject identifier as a string.
        """
        record = self.get_selected_subject_record()
        if record:
            return record.get("subject", "")
        data = self.subject_dropdown.currentData()
        return str(data) if data else ""


    def get_selected_file_tag(self):
        """
        Return file_tag for the selected H5 record, if available.
        """
        record = self.get_selected_subject_record()
        if record:
            return record.get("file_tag", "")
        return ""


    def get_annotation_output_folder(self):
        """
        Return the annotation output folder for the current subject/user.

        New H5 structure:
            record["output_path"] / username

        Old fallback:
            base_folder / subject / output / username
        """
        user_name = self.get_user_name()
        subject = self.get_selected_subject_name()
        base_folder = getattr(self, "base_folder", None)
        record = self.get_selected_subject_record()

        if not user_name or not subject:
            return None

        if record and record.get("output_path"):
            return os.path.join(record["output_path"], user_name)

        if base_folder:
            return os.path.join(base_folder, subject, "output", user_name)

        return None


    def get_annotation_filenames(self):
        """
        Return partial and complete annotation filenames for the current selection.
        """
        subject = self.get_selected_subject_name()
        user_name = self.get_user_name()
        file_tag = self.get_selected_file_tag()

        # Include file_tag if present for readability and extra collision protection.
        if file_tag:
            base = f"annotations_{subject}_{file_tag}_{user_name}"
        else:
            base = f"annotations_{subject}_{user_name}"

        return f"{base}.csv", f"{base}_COMPLETE.csv"

    def update_table_data(self):
        self.ann_table.setRowCount(len(self.annotations))
        for idx, ann in enumerate(self.annotations):
            user = ann.get("user", "")
            subject = ann.get("subject", "")
            cpr = ann.get("cpr", "")
            rhythm = ann.get("rhythm_label", "")
            signal_exp = ann.get("rhythm_expl", "")
            start = ann.get("start", "")
            end = ann.get("end", "")

            row_data = [
                user,
                subject,
                cpr,
                rhythm,
                signal_exp,
                str(start),
                str(end)
            ]
            for col, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                self.ann_table.setItem(idx, col, item)

        self.remove_last_btn.setDisabled(len(self.annotations) == 0)

    def update_waveform_and_mark(self):
        """
        Timed wrapper around annotation and pending-marker graphics rebuilding.
        """
        before_counts = self._get_plot_item_counts()
        start_time = perf_counter()

        try:
            return self._update_waveform_and_mark_impl()
        finally:
            elapsed = perf_counter() - start_time
            after_counts = self._get_plot_item_counts()

            self._perf_log(
                "update_waveform_and_mark",
                elapsed,
                annotations=len(
                    getattr(self, "annotations", [])
                ),
                items_before=before_counts["total"],
                items_after=after_counts["total"],
                regions_after=after_counts["regions"],
                text_after=after_counts["text_items"],
                lines_after=after_counts["infinite_lines"],
            )


    def _update_waveform_and_mark_impl(self):
        marker = getattr(self, "current_marker", None)
        last_mark = getattr(self, "last_mark", None)
        annotations = getattr(self, "annotations", [])
        print(f'ann: {annotations}')
        # ---- REMOVE all overlays first (except main waveform line) ----
        # Only remove LinearRegionItem, TextItem, InfiniteLine (markers), not data lines
        for plot in self.waveform_plots:
            items_to_remove = []
            for item in list(plot.items()):
                if isinstance(item, pg.LinearRegionItem):
                    items_to_remove.append(item)

                elif isinstance(item, pg.TextItem):
                    if not getattr(item, "is_event_marker", False):
                        items_to_remove.append(item)

                elif isinstance(item, pg.InfiniteLine):
                    if getattr(item, "is_marker", False) and not getattr(item, "is_event_marker", False):
                        items_to_remove.append(item)
            for itm in items_to_remove:
                plot.removeItem(itm)

        # ---- Pending region (current mark, not yet confirmed/added to self.annotations) ----
        if self.current_marker is not None and self.last_mark is not None and self.current_marker > self.last_mark:
            color = (255, 215, 0, 55)  # example: U-M maize, semi-transparent
            for plot in self.waveform_plots:
                region = pg.LinearRegionItem([last_mark, marker], brush=pg.mkBrush(color), movable=False)
                plot.addItem(region)
                # Add a "Pending" label at center top of region
                y_max = plot.viewRange()[1][1]
                label_item = pg.TextItem("Pending", color='#00274C', anchor=(0.5, 1))
                label_item.setPos(last_mark + (marker - last_mark) / 2, y_max)
                plot.addItem(label_item)

        # ---- Finalized/Confirmed annotation overlays from self.annotations ----
        for ann in annotations:
            start = ann.get("start", None)
            end = ann.get("end", None)
            rhythm = ann.get("rhythm_label", "")
            print(f'start: {start}')
            print(f'end: {end}')
            print(f'rhythm: {rhythm}')
            ann_color = LABEL_COLORS.get(rhythm, (180, 180, 180, 60))
            if isinstance(ann_color, tuple) and len(ann_color) == 3:
                ann_color = (*ann_color, 60)  # Add alpha channel if missing
            if start is not None and end is not None and end > start:
                for plot in self.waveform_plots:
                    # Draw colored region overlay
                    region = pg.LinearRegionItem([start, end], brush=pg.mkBrush(ann_color), movable=False)
                    plot.addItem(region)
                    # Add region end label (use same color, but RGB only)
                    y_max = plot.viewRange()[1][1]
                    text_color = ann_color[:3] if len(ann_color) >= 3 else (0, 0, 0)
                    label_item = pg.TextItem(rhythm, color=text_color, anchor=(1, 1))
                    rect = label_item.boundingRect()
                    vb = plot.getViewBox()
                    y_max = plot.viewRange()[1][1]
                    y_min = plot.viewRange()[1][0]
                    y_offset = 0.25 * (y_max - y_min) 
                    x0 = vb.mapToView(QtCore.QPointF(0, 0)).x()
                    x1 = vb.mapToView(QtCore.QPointF(rect.width(), 0)).x()
                    label_offset_x = 0 if rect.width() == 0 else abs(x1 - x0)
                    label_item.setPos(end - label_offset_x, y_max - y_offset)
                    plot.addItem(label_item)
                    # Optionally: draw a vertical line at region end
                    vline = pg.InfiniteLine(pos=end, angle=90, pen=pg.mkPen('#222', style=pg.QtCore.Qt.DotLine))
                    vline.is_marker = True
                    plot.addItem(vline)
                    print(f"Added region from {start} to {end} on plot with x-range {self.waveform_plots[0].viewRange()[0]}")
        
        # ---- Draw (pending) marker vline if set ----
        if marker is not None:
            for plot in self.waveform_plots:
                marker_line = pg.InfiniteLine(pos=marker, angle=90, pen='r')
                marker_line.is_marker = True
                plot.addItem(marker_line)

        # ---- Restrict scroll/zoom to X only ----
        for plot in self.waveform_plots:
            plot.getViewBox().setMouseEnabled(x=True, y=False)
            # Optionally: autoscale y range for each plot
            # plot.enableAutoRange(axis='y', enable=True)


    def set_scrollbar_range(self, minval, maxval, val):
        self.x_scrollbar.blockSignals(True)
        self.x_scrollbar.setMinimum(int(minval))
        self.x_scrollbar.setMaximum(int(maxval))
        self.x_scrollbar.setValue(int(val))
        self.x_scrollbar.blockSignals(False)


    def save_all_to_file(self):
        """
        Timed wrapper around manual annotation saving and dropdown refresh.
        """
        start_time = perf_counter()

        try:
            return self._save_all_to_file_impl()
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "save_all_to_file TOTAL",
                elapsed,
                annotations=len(
                    getattr(self, "annotations", [])
                ),
            )


    def _save_all_to_file_impl(self):
        annotations = getattr(self, "annotations", [])
        subject = self.get_selected_subject_name()
        user_name = self.get_user_name()
        base_folder = getattr(self, "base_folder", None)

        if not annotations:
            self.save_message.setText("No annotations to save.")
            return

        if not subject or not base_folder or not user_name:
            self.save_message.setText("Subject, base folder, or User Name not set.")
            return

        output_folder = self.get_annotation_output_folder()
        if not output_folder:
            self.save_message.setText("Could not determine annotation output folder.")
            return

        os.makedirs(output_folder, exist_ok=True)

        partial_filename, complete_filename = self.get_annotation_filenames()

        partial_path = os.path.join(output_folder, partial_filename)
        complete_path = os.path.join(output_folder, complete_filename)

        if getattr(self, "waveform_complete", False):
            fullpath = complete_path

            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                    print(f"Deleted partial annotation file: {partial_path}")
                except Exception as e:
                    print(f"Warning: Could not delete partial annotation file: {e}")
        else:
            fullpath = partial_path

            if os.path.exists(complete_path):
                try:
                    os.remove(complete_path)
                    print(f"Deleted complete annotation file after reverting to partial: {complete_path}")
                except Exception as e:
                    print(f"Warning: Could not delete complete annotation file: {e}")

        # Save Timer Start
        csv_write_start = perf_counter()

        pd.DataFrame(annotations).to_csv(
            fullpath,
            index=False,
        )

        # Save Timer Calculation
        csv_write_elapsed = perf_counter() - csv_write_start
        self._perf_log(
            "manual_save_csv_write",
            csv_write_elapsed,
            rows=len(annotations),
            path=fullpath,
        )
        self.save_message.setText(f"Saved to {fullpath}")

        # Maintain refresh on manual save
        self.refresh_selected_record_annotation_status()


    def autosave_annotations(self):
        """
        Timed wrapper around autosave and completion-count refresh.
        """
        start_time = perf_counter()

        try:
            return self._autosave_annotations_impl()
        finally:
            elapsed = perf_counter() - start_time

            self._perf_log(
                "autosave_annotations TOTAL",
                elapsed,
                annotations=len(
                    getattr(self, "annotations", [])
                ),
            )
            

    def _autosave_annotations_impl(self):
        annotations = getattr(self, "annotations", [])
        subject = self.get_selected_subject_name()
        user_name = self.get_user_name()
        base_folder = getattr(self, "base_folder", None)

        if not annotations or not subject or not base_folder or not user_name:
            return

        output_folder = self.get_annotation_output_folder()

        if not output_folder:
            return

        os.makedirs(output_folder, exist_ok=True)

        partial_filename, complete_filename = self.get_annotation_filenames()

        partial_path = os.path.join(
            output_folder,
            partial_filename,
        )
        complete_path = os.path.join(
            output_folder,
            complete_filename,
        )

        if getattr(self, "waveform_complete", False):
            fullpath = complete_path

            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                    print(
                        "Deleted partial annotation file: "
                        f"{partial_path}"
                    )
                except Exception as exc:
                    print(
                        "Warning: Could not delete partial annotation "
                        f"file: {exc}"
                    )
        else:
            fullpath = partial_path

            if os.path.exists(complete_path):
                try:
                    os.remove(complete_path)
                    print(
                        "Deleted complete annotation file after "
                        f"reverting to partial: {complete_path}"
                    )
                except Exception as exc:
                    print(
                        "Warning: Could not delete complete annotation "
                        f"file: {exc}"
                    )

        # Save Timer Start
        csv_write_start = perf_counter()

        pd.DataFrame(annotations).to_csv(
            fullpath,
            index=False,
        )

        # Save Timer Calculation
        csv_write_elapsed = perf_counter() - csv_write_start
        self._perf_log(
            "autosave_csv_write",
            csv_write_elapsed,
            rows=len(annotations),
            path=fullpath,
        )
        self.save_message.setText(f"Auto-saved to {fullpath}")

        # Possible slow-down
        #self.refresh_subject_dropdown_preserve_selection()

    # --- Utility slots for GUI logic that you will implement: ---
    def get_cpr_val(self):
        if self.cpr_yes.isChecked():
            return "Yes"
        if self.cpr_no.isChecked():
            return "No"
        if self.cpr_U2D.isChecked():
            return "Unable to Determine"
        return None


    def clear_cpr(self):
        self.cpr_group.setExclusive(False)
        self.cpr_yes.setChecked(False)
        self.cpr_no.setChecked(False)
        self.cpr_U2D.setChecked(False)
        self.cpr_group.setExclusive(True)
        self.cpr_yes.setDisabled(True)
        self.cpr_no.setDisabled(True)
        self.cpr_U2D.setDisabled(True)
