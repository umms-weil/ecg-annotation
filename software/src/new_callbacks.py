import os
import numpy as np
import pandas as pd
from datetime import datetime
from processing import list_subjects, load_waveforms_for_subject, get_code_time_bounds, get_events_for_window, datetime_string_to_seconds_since_1970
from PyQt5.QtWidgets import QTableWidgetItem, QMessageBox
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
import pyqtgraph as pg

UM_MAIZE = "#FFCB05"
UM_BLUE = "#00274C"
UM_ACCENT = "#285680"
UM_WHITE = "#FFFFFF"
UM_RED = "#D50032"
COMPLETION_GREEN = "#199E40"

# LABEL_COLORS = {
#     "Normal Heart Rhythm": "LightGreen",
#     "Sinus tachycardia": "LightBlue",
#     "Bradycardia": "Khaki",
#     "Supraventricular tachycardia": "Tomato",
#     "Atrial Flutter": "Lavender",
#     "Atrial Fibrillation": "SlateGray",
#     "Ventricular Tachycardia": "Orange",
#     "Ventricular Fibrillation": "Red",
#     "Atrial Pacing Rhythm": "Gold",
#     "Ventricular Pacing Rhythm": "Teal",
#     "Idioventricular Rhythm": "Purple"
# }
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

class RelativeAxis(pg.AxisItem):
    def __init__(self, t0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.t0 = t0

    def tickStrings(self, values, scale, spacing):
        # Display ticks as seconds from the recording start
        return [f"{v - self.t0:.1f}" for v in values]

class AnnotationAppCallbacks:
    def set_base_folder(self):
        folder_path = self.folder_input.text()
        print("SET FOLDER CLICKED", folder_path)
        if not folder_path or not os.path.isdir(folder_path):
            self.base_folder = ""
            self.folder_status.setText("❌ Invalid folder.")
            return
        self.base_folder = folder_path
        self.folder_status.setText(f"📂 Base folder set: {folder_path}")
        self.update_subject_dropdown()


    def update_subject_dropdown(self):
        base_folder = getattr(self, 'base_folder', None)
        combo = self.subject_dropdown
        combo.clear()
        combo.setDisabled(True)
        if not base_folder or not os.path.isdir(base_folder):
            return
        subjects = list_subjects(base_folder)
        for subj in subjects:
            output_folder = os.path.join(base_folder, subj["name"], "output")
            total_annotations = 0
            complete_annotations = 0

            if os.path.isdir(output_folder):
                # Go through each user subfolder inside the output folder
                user_folders = [os.path.join(output_folder, u) for u in os.listdir(output_folder) 
                                if os.path.isdir(os.path.join(output_folder, u))]
                for user_folder in user_folders:
                    files = [f for f in os.listdir(user_folder) if f.endswith('.csv')]
                    total_annotations += len(files)
                    complete_annotations += sum(1 for f in files if f.endswith('_COMPLETE.csv'))

            if total_annotations > 0:
                label = f"✅ {subj['name']} ({complete_annotations}/{total_annotations} complete)"
            else:
                label = f"⭕ {subj['name']} (0/0 complete)"
            combo.addItem(label, userData=subj["name"])
        combo.setDisabled(False)


    def autoscale_y(self, plot, signal):
        """
        Autoscale the y-axis of the given PlotWidget to fit the central 99% of signal values,
        avoiding huge artifacts or outliers.
        
        Parameters:
        - plot: The pyqtgraph PlotWidget to set the Y range.
        - signal: The 1D numpy array of waveform values.
        """
        if signal is None or len(signal) == 0:
            return
        p_lo, p_hi = np.percentile(signal, [0.5, 99.5])
        # Find the "span from zero" to max(abs) percentile
        half_span = max(abs(p_lo), abs(p_hi))
        margin = 0.1 * half_span if half_span > 0 else 1.0
        y_min = -half_span - margin
        y_max = half_span + margin
        plot.setYRange(y_min, y_max, padding=0)


    def adjust_y_scale(self, plot_idx, zoom="up"):
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
        Autoscale one plot's Y-axis using the current visible X-window plus buffer.

        Parameters
        ----------
        plot_idx : int
            Index of the plot/lead to autoscale.
        force : bool
            If True, perform autoscale even if this method was called directly.
            The max-window limit is still respected.
        """
        if not hasattr(self, "time_axis") or self.time_axis is None:
            return False
        if not hasattr(self, "leads_ds") or self.leads_ds is None:
            return False
        if plot_idx < 0 or plot_idx >= len(self.waveform_plots):
            return False
        if plot_idx >= len(self.leads_ds):
            return False

        sig = self.leads_ds[plot_idx]
        if sig is None:
            return False

        time_axis = np.asarray(self.time_axis, dtype=float)
        sig = np.asarray(sig, dtype=float)

        if time_axis.size == 0 or sig.size == 0:
            return False

        # Protect against length mismatch.
        n = min(time_axis.size, sig.size)
        time_axis = time_axis[:n]
        sig = sig[:n]

        try:
            x_min, x_max = self.waveform_plots[0].viewRange()[0]
            x_min = float(x_min)
            x_max = float(x_max)
        except Exception:
            return False

        visible_span = x_max - x_min
        max_window = getattr(self, "max_auto_y_window_sec", 300.0)

        if visible_span > max_window:
            self.update_all_auto_y_button_states()
            return False

        buffer_sec = getattr(self, "auto_y_buffer_sec", 10.0)

        scale_start = max(float(time_axis[0]), x_min - buffer_sec)
        scale_end = min(float(time_axis[-1]), x_max + buffer_sec)

        if scale_end <= scale_start:
            return False

        # Fast slicing using sorted time axis.
        i0 = np.searchsorted(time_axis, scale_start, side="left")
        i1 = np.searchsorted(time_axis, scale_end, side="right")

        if i1 <= i0:
            return False

        segment = sig[i0:i1]
        segment = segment[np.isfinite(segment)]

        if segment.size < 2:
            return False

        try:
            y_lo, y_hi = np.nanpercentile(segment, [0.5, 99.5])
        except Exception:
            return False

        if not np.isfinite(y_lo) or not np.isfinite(y_hi):
            return False

        span = y_hi - y_lo
        min_span = getattr(self, "auto_y_min_span", 0.25)
        margin_fraction = getattr(self, "auto_y_margin_fraction", 0.05)

        if span <= 0:
            center = (y_hi + y_lo) / 2.0
            y_min = center - min_span / 2.0
            y_max = center + min_span / 2.0
        else:
            margin = max(span * margin_fraction, min_span * margin_fraction)
            y_min = y_lo - margin
            y_max = y_hi + margin

        self.waveform_plots[plot_idx].setYRange(y_min, y_max, padding=0)
        return True
        
    def plot_event_markers(self):
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
                label = pg.TextItem(event_name, color="#FF0808", anchor=(0, 0))
                font = QFont('Arial')
                font.setPointSize(20)
                label.setFont(font)
                label.setPos(event_sec, label_y)
                label.setZValue(100)
                plot.addItem(label)
                self.event_labels.append(label)
        
        # Put in the Code start and End as Red markers
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
        event_color = (128, 128, 0)
        event_pen   = pg.mkPen(event_color, width=5, style=QtCore.Qt.DashLine)
        for plot in self.waveform_plots:
            y_min, y_max = plot.viewRange()[1]
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
        # Clear all plots and set up axis
        for plot in self.waveform_plots:
            plot.clear()

        t0 = self.time_axis[0]   # Epic time, start of window

        # Set axis: shows epic time ticks
        for plt in self.waveform_plots:
            plt.setAxisItems({'bottom': RelativeAxis(t0, orientation='bottom')})

        # Plot signals on epic time axis
        for i, (plot, sig, name) in enumerate(zip(self.waveform_plots, self.leads_ds, self.lead_names)):
            # Set y-axis label to real lead name with units
            plot.setLabel(
                'left',
                f"{name} (mV)",
                color=UM_BLUE,
                size="10pt"
            )
            if sig is not None and len(sig) > 0:
                plot.plot(self.time_axis, sig, pen='b', name=name)
                plot.setTitle(name)

                # Autoscale Y axis (center at zero)
                p_lo, p_hi = np.percentile(sig, [0.5, 99.5])
                half_span = max(abs(p_lo), abs(p_hi))
                margin = 0.1 * half_span if half_span > 0 else 1.0
                y_min = -half_span - margin
                y_max = half_span + margin
                plot.setYRange(y_min, y_max, padding=0)
            else:
                plot.setTitle(f"{name} (no data)")

        # Set initial X range (epic time)
        winlen = float(self.win_size.value()) if hasattr(self, 'win_size') else 10
        left = self.time_axis[0]
        right = left + winlen
        self.waveform_plots[0].setXRange(left, right, padding=0)
        for plt in self.waveform_plots[1:]:
            plt.setXLink(self.waveform_plots[0])
            
        # ---- Restrict scroll/zoom to X only ----
        for plot in self.waveform_plots:
            plot.getViewBox().setMouseEnabled(x=True, y=False)
            # Optionally: autoscale y range for each plot
            # plot.enableAutoRange(axis='y', enable=True)

         # Plot event markers AFTER plotting leads
        if hasattr(self, 'manifest_events') and self.manifest_events is not None:
            self.plot_event_markers()


    def handle_remove_last_mark(self):
        """
        Removes the most recent annotation ('last mark') from table and plots.
        Resets sidebar and markers to previous state or initial if no marks remain.
        """
        if not self.annotations:
            # Nothing to remove
            return

        # Remove last annotation
        removed_ann = self.annotations.pop()
        print(f"Removed last annotation: {removed_ann}")

        # Reset completion flag if removed interval was at waveform end
        waveform_end = self.time_axis[-1]
        # Only set to False if annotation table is now empty or last annotation does NOT end at waveform end
        if not self.annotations or self.annotations[-1]["end"] != waveform_end:
            self.waveform_complete = False

        # Reset last_mark to previous annotation end (if any), else initial
        if self.annotations:
            self.last_mark = self.annotations[-1]['end']
        else:
            # If no annotations, reset to initial state (e.g., start of data or None)
            self.last_mark = None
            self.current_marker = None

        # Clear pending marker (you may want to clear other sidebar fields too)
        self.current_marker = None

        # Update the UI: table, plots, sidebar
        self.update_table_data()
        self.update_waveform_and_mark()
        self.update_sidebar_ui()

    def handle_load_annotation(self):
        print("LOAD ANNOTATIONS BUTTON CLICKED")
        user_name = self.username_input.currentText().strip()
        subject = self.subject_dropdown.currentData()

        # --- Username check ---
        if not user_name:
            # Style update, as discussed
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
        subject_folder = os.path.join(self.base_folder, subject)
        user_name = self.username_input.currentText().strip()
        output_folder = os.path.join(subject_folder, "output", user_name)
        filename = f"annotations_{subject}_{user_name}.csv"
        fullpath = os.path.join(output_folder, filename)

        # --- File existence check ---
        if not os.path.exists(fullpath):
            self.mark_warning.setText(
                f"No previous annotations found for '{user_name}' and subject '{subject}'."
            )
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        # --- Load the annotation file ---
        try:
            df = pd.read_csv(fullpath)
            # Convert DataFrame to list of dicts for self.annotations
            # Assumes CSV columns: user, subject, cpr, rhythm_label, rhythm_expl, start, end
            self.annotations = df.to_dict(orient='records')
        except Exception as e:
            self.mark_warning.setText(f"Failed to load annotations: {e}")
            self.mark_warning.setWordWrap(True)
            self.mark_warning.setStyleSheet("color: #B71234; font-size: 13px; font-weight: bold;")
            return

        # --- Sync table and plots to match loaded annotations ---
        self.update_table_data()
        self.update_waveform_and_mark()
        self.update_sidebar_ui()

        # --- Set marker state for continued marking ---
        if self.annotations:
            self.last_mark = self.annotations[-1]['end']
            self.current_marker = None  # Reset for next marking
        else:
            self.last_mark = None
            self.current_marker = None

        # --- Center plot(s) on last annotation's end if loaded ---
        if self.annotations:
            last_mark_end = self.annotations[-1]["end"]
            winlen = float(self.win_size.value()) if hasattr(self, 'win_size') else 10
            left = max(last_mark_end - winlen / 2, self.time_axis[0])
            right = left + winlen
            self.waveform_plots[0].setXRange(left, right, padding=0)
            for plt in self.waveform_plots[1:]:
                plt.setXLink(self.waveform_plots[0])

        # --- Show annotation session resume message and file modification date ---
        try:
            mod_time = os.path.getmtime(fullpath)
            import datetime
            dt_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            self.mark_warning.setText(
                f"Resuming annotation session for '{user_name}' on '{subject}'.\n"
                f"Last saved: {dt_str}"
            )
            self.mark_warning.setStyleSheet("color: #285680; font-size: 13px; font-weight: bold;")
            self.mark_warning.setWordWrap(True)
        except Exception:
            self.mark_warning.setText(
                f"Resuming annotation session for '{user_name}' on '{subject}'."
            )
            self.mark_warning.setStyleSheet("color: #285680; font-size: 13px; font-weight: bold;")
            self.mark_warning.setWordWrap(True)

    def load_subject_data(self):
        subject_idx = self.subject_dropdown.currentIndex()
        if subject_idx < 0:
            print("No subject selected.")
            return
        subject_name = self.subject_dropdown.itemData(subject_idx)
        base_folder = getattr(self, 'base_folder', None)
        print(f"Button clicked: load subject {subject_name} from {base_folder}")
        if not subject_name or not base_folder or not os.path.isdir(base_folder):
            print('No data loaded.')
            self.data_store = {}
            return
        code_csv_path = '/Users/pwalczyk/Documents/Projects/Uconn-CPR/AnnotationSoftware/ecg-annotation/software/data/waveform_manifest.csv'
        # code_csv_path = '/Users/pwalczyk/Documents/Projects/Uconn-CPR/AnnotationSoftware/ecg-annotation/software/data/data/FAKE_DATA/waveform_manifest.csv'
        self.recording_start_sec, self.recording_end_sec, code_start_sec, code_stop_sec = get_code_time_bounds(subject_name, code_csv_path)
        loaded_waveforms = load_waveforms_for_subject(
            base_folder, subject_name,
            recording_start_sec=self.recording_start_sec,
            code_start_sec=code_start_sec,
            code_stop_sec=code_stop_sec,
            desired_waveforms=["I", "II", "III", "V", "AVF", "AVL", "AVR"]
        )
        print(type(loaded_waveforms))
        print(loaded_waveforms)
        times_ds   = loaded_waveforms.get('times_ds', None)
        leads_ds   = loaded_waveforms.get('leads_ds', None)
        lead_names = loaded_waveforms.get('lead_names', None)
        units      = loaded_waveforms.get('units', None)
        Fs         = loaded_waveforms.get('Fs', None)

        print(times_ds, leads_ds, lead_names, units, Fs)
        # --- Filter manifest events for current subject and code window ---
        manifest_events_df = get_events_for_window(
            code_csv_path, subject_name, code_start_sec, code_stop_sec
        )
        manifest_events_df['event_sec'] = manifest_events_df['RECORDED_TIME'].apply(datetime_string_to_seconds_since_1970)
        manifest_events_df = manifest_events_df.drop_duplicates(subset=['FLO_MEAS_NAME', 'FLOWSHEET_VALUE', 'RECORDED_TIME'])
        print(manifest_events_df)
        self.manifest_events = manifest_events_df

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
    
        self.data_store = {
            "time": times_ds.tolist() if hasattr(times_ds, "tolist") else list(times_ds),
            "leads": [l.tolist() if l is not None else None for l in leads_ds],
            "lead_names": lead_names,
            "subject": subject_name,
        }
        self.annotations = []
        print("Loaded data for:", subject_name)
        # After assigning self.time_axis, self.leads_ds, self.lead_names:
        # --- Pass code bounds, events to the plotting function ---
        self.code_start_sec = code_start_sec
        self.code_stop_sec  = code_stop_sec

        # Set waveform complete flag to False for new subject load, which controls whether marking is allowed
        self.waveform_complete = False
        
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
            vb = self.waveform_plots[lead_idx].getViewBox()
            mouse_point = vb.mapSceneToView(mouse_event.scenePos())
            t_clicked = float(mouse_point.x())

            waveform_end = self.time_axis[-1]
            if t_clicked > waveform_end:
                # Snap to end of waveform if clicked beyond it
                t_clicked = waveform_end
            elif (waveform_end - t_clicked) <= 1.0:
                # Snap to end if within 1 second on waveform (due to 1 second min rhythm marking requirement)
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
        print("handle_mark_clicked CALLED")
        if (
            self.current_marker is not None
            and self.last_mark is not None
            and self.current_marker > self.last_mark
        ):
            rhythm_label = self.rhythm_dropdown.currentText() if self.rhythm_dropdown.isEnabled() else None

            ann = {
                "user": self.username_input.currentText().strip(),
                "subject": self.subject_dropdown.currentData(),
                "cpr": self.get_cpr_val(),
                "rhythm_label": self.rhythm_dropdown.currentText() if self.rhythm_dropdown.isEnabled() else "",
                "rhythm_expl": self.rhythm_explanation.toPlainText(),
                "start": self.last_mark,
                "end": self.current_marker,
            }
            print(f"APPENDING ANNOTATION: {ann}")
            self.annotations.append(ann)

            # Completion detection logic
            waveform_end = self.time_axis[-1]
            if self.current_marker == waveform_end:
                # If this is the last mark needed
                self.waveform_complete = True
                self.mark_warning.setText("Waveform annotation complete! No further marking needed.")
                self.mark_warning.setStyleSheet("font-size:13px; font-weight:bold; color:#199E40;")
                # Trigger save and disable further marking
                self.save_all_to_file()
                self.mark_btn.setDisabled(True)
            else:
                # Prepare for next marking
                self.last_mark = self.current_marker
                self.current_marker = None
                self.pending_clear_sidebar = True
                self.update_sidebar_ui()
        else:
            print("Attempted to mark invalid or zero-length region.")

        self.update_sidebar_ui()
        self.update_waveform_and_mark()
        self.update_table_data()
        print("Current ANNOTATIONS LIST after marking:", self.annotations)


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
        marker = getattr(self, "current_marker", None)
        last_mark = getattr(self, "last_mark", None)
        annotations = getattr(self, "annotations", [])
        print(f'ann: {annotations}')
        # ---- REMOVE all overlays first (except main waveform line) ----
        # Only remove LinearRegionItem, TextItem, InfiniteLine (markers), not data lines
        for plot in self.waveform_plots:
            items_to_remove = []
            for item in list(plot.items()):
                if isinstance(item, (pg.LinearRegionItem, pg.TextItem)) or (
                    isinstance(item, pg.InfiniteLine) and getattr(item, 'is_marker', False)
                ):
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
        annotations = getattr(self, "annotations", [])
        subject = self.subject_dropdown.currentData()
        user_name = self.username_input.currentText().strip()
        base_folder = getattr(self, "base_folder", None)

        if not annotations:
            self.save_message.setText("No annotations to save.")
            return
        if not subject or not base_folder or not user_name:
            self.save_message.setText("Subject, base folder, or User Name not set.")
            return

        subject_folder = os.path.join(base_folder, subject)
        user_name = self.username_input.currentText().strip()
        output_folder = os.path.join(subject_folder, "output", user_name)
        os.makedirs(output_folder, exist_ok=True)

        # Determine completion
        if getattr(self, "waveform_complete", False):
            filename = f"annotations_{subject}_{user_name}_COMPLETE.csv"
            partial_filename = f"annotations_{subject}_{user_name}.csv"
            partial_path = os.path.join(output_folder, partial_filename)
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                    print(f"Deleted partial annotation file: {partial_path}")
                except Exception as e:
                    print(f"Warning: Could not delete partial annotation file: {e}")
        else:
            filename = f"annotations_{subject}_{user_name}.csv"

        fullpath = os.path.join(output_folder, filename)
        pd.DataFrame(annotations).to_csv(fullpath, index=False)
        self.save_message.setText(f"Saved to {fullpath}")


    def autosave_annotations(self):
        annotations = getattr(self, "annotations", [])
        subject = self.subject_dropdown.currentData()
        user_name = self.username_input.currentText().strip()
        base_folder = getattr(self, "base_folder", None)

        if not annotations or not subject or not base_folder or not user_name:
            return

        subject_folder = os.path.join(base_folder, subject)
        user_name = self.username_input.currentText().strip()
        output_folder = os.path.join(subject_folder, "output", user_name)
        os.makedirs(output_folder, exist_ok=True)

        if getattr(self, "waveform_complete", False):
            filename = f"annotations_{subject}_{user_name}_COMPLETE.csv"
            partial_filename = f"annotations_{subject}_{user_name}.csv"
            partial_path = os.path.join(output_folder, partial_filename)
            if os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                    print(f"Deleted partial annotation file: {partial_path}")
                except Exception as e:
                    print(f"Warning: Could not delete partial annotation file: {e}")
        else:
            filename = f"annotations_{subject}_{user_name}.csv"

        fullpath = os.path.join(output_folder, filename)
        pd.DataFrame(annotations).to_csv(fullpath, index=False)
        self.save_message.setText(f"Auto-saved to {fullpath}")

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
