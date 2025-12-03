import os
import numpy as np
import pandas as pd
from datetime import datetime
from processing import list_subjects, load_waveforms_for_subject, get_code_time_bounds, get_events_for_window, datetime_string_to_seconds_since_1970
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5 import QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
import pyqtgraph as pg


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
            n_annotations = 0
            has_annotations = False
            if os.path.isdir(output_folder):
                # Count all CSV files in the output folder:
                files = [f for f in os.listdir(output_folder) if f.endswith('.csv')]
                n_annotations = len(files)
                has_annotations = n_annotations > 0
            if has_annotations:
                label = f"✅ {subj['name']} ({n_annotations} annots)"
            else:
                label = f"⭕ {subj['name']} (0 annots)"
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
        plt = self.waveform_plots[plot_idx]
        y_min, y_max = plt.viewRange()[1]
        center = (y_min + y_max) / 2
        span = (y_max - y_min) or 1.0
        if zoom == "up":
            new_span = span * 0.8  # Zoom in
        elif zoom == "down":
            new_span = span * 1.25 # Zoom out
        else:
            new_span = span
        new_min = center - new_span / 2
        new_max = center + new_span / 2
        plt.setYRange(new_min, new_max, padding=0)

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
        
        self.plot_all_leads()

        self.update_waveform_and_mark()
        self.update_table_data()

    def update_sidebar_ui(self):
        # ===== FULL SIDEBAR CLEAR, after MARK =====
        if getattr(self, "pending_clear_sidebar", False):
            self.pending_clear_sidebar = False

            # ---- Interpretable radios: clear and enable for new selection
            self.interp_group.setExclusive(False)
            self.radio_interp_yes.setChecked(False)
            self.radio_interp_no.setChecked(False)
            self.interp_group.setExclusive(True)
            self.radio_interp_yes.setDisabled(False)
            self.radio_interp_no.setDisabled(False)

            # ---- Comment: clear, disable
            self.comment_box.blockSignals(True)
            self.comment_box.setPlainText("")
            self.comment_box.setDisabled(True)
            self.comment_box.blockSignals(False)

            # ---- Cardiac Arrest radios ----
            self.ca_group.setExclusive(False)
            self.cardiac_arrest_yes.setChecked(False)
            self.cardiac_arrest_no.setChecked(False)
            self.ca_group.setExclusive(True)
            self.cardiac_arrest_yes.setDisabled(True)
            self.cardiac_arrest_no.setDisabled(True)

            # ---- CPR radios ----
            self.cpr_group.setExclusive(False)
            self.cpr_yes.setChecked(False)
            self.cpr_no.setChecked(False)
            self.cpr_group.setExclusive(True)
            self.cpr_yes.setDisabled(True)
            self.cpr_no.setDisabled(True)

            # ---- Rhythm dropdown ----
            self.rhythm_dropdown.blockSignals(True)
            self.rhythm_dropdown.setCurrentIndex(-1)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_dropdown.blockSignals(False)

            # ---- Rhythm explanation ----
            self.rhythm_explanation.blockSignals(True)
            self.rhythm_explanation.setPlainText("")
            self.rhythm_explanation.setDisabled(True)
            self.rhythm_explanation.blockSignals(False)

            # --- Mark warning/mark btn: clear and disable
            self.mark_warning.setText("")
            self.mark_btn.setDisabled(True)
            return

        # ======= Proceed with step logic =======
        interp = self.get_interp_val()
        ca = self.get_ca_val()
        cpr = self.get_cpr_val()
        rhythm = self.rhythm_dropdown.currentText() if self.rhythm_dropdown.isEnabled() else None
        comment = self.comment_box.toPlainText()
        rex = self.rhythm_explanation.toPlainText()
        user_name = self.username_input.text()
        marker = self.current_marker
        last_mark = self.last_mark
        warning = self.mark_warning.text()

        # Stepwise field enables/disables
        if interp is None:
            # Step 1: Only Interpretable enabled
            self.radio_interp_yes.setDisabled(False)
            self.radio_interp_no.setDisabled(False)
            self.cardiac_arrest_yes.setDisabled(True)
            self.cardiac_arrest_no.setDisabled(True)
            self.cpr_yes.setDisabled(True)
            self.cpr_no.setDisabled(True)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_explanation.setDisabled(True)
            self.comment_box.setDisabled(True)
        elif interp == "No":
            # Step 2a: Non-interpretable, comment only
            self.radio_interp_yes.setDisabled(False)
            self.radio_interp_no.setDisabled(False)
            self.cardiac_arrest_yes.setDisabled(True)
            self.cardiac_arrest_no.setDisabled(True)
            self.cpr_yes.setDisabled(True)
            self.cpr_no.setDisabled(True)
            self.rhythm_dropdown.setDisabled(True)
            self.rhythm_explanation.setDisabled(True)
            self.comment_box.setDisabled(False)
        elif interp == "Yes":
            # Step 2b: Interpretable, ask Cardiac Arrest
            self.radio_interp_yes.setDisabled(False)
            self.radio_interp_no.setDisabled(False)
            self.cardiac_arrest_yes.setDisabled(False)
            self.cardiac_arrest_no.setDisabled(False)

            if ca is None:
                # Must pick CA to continue
                self.cpr_yes.setDisabled(True)
                self.cpr_no.setDisabled(True)
                self.rhythm_dropdown.setDisabled(True)
                self.rhythm_explanation.setDisabled(True)
                self.comment_box.setDisabled(False)
            elif ca == "Yes":
                # Now ask CPR
                self.cpr_yes.setDisabled(False)
                self.cpr_no.setDisabled(False)
                self.rhythm_dropdown.setDisabled(True)
                self.rhythm_explanation.setDisabled(True)
                self.comment_box.setDisabled(False)
            elif ca == "No":
                # Now ask rhythm and maybe explanation
                self.cpr_yes.setDisabled(True)
                self.cpr_no.setDisabled(True)
                self.rhythm_dropdown.setDisabled(False)
                # Rhythm Explanation requirement:
                if rhythm in ["Other", "Unable to Determine"]:
                    self.rhythm_explanation.setDisabled(False)
                else:
                    self.rhythm_explanation.setDisabled(True)
                self.comment_box.setDisabled(False)
            else:
                # Should not happen, defensive fallback
                self.cpr_yes.setDisabled(True)
                self.cpr_no.setDisabled(True)
                self.rhythm_dropdown.setDisabled(True)
                self.rhythm_explanation.setDisabled(True)
                self.comment_box.setDisabled(False)

        # Always ensure Mark button & warning are set appropriately
        warning_msg = ""
        mark_btn_disabled = False

        # --- Below is workflow for enabling Mark ---
        if marker is None:
            warning_msg = "Click on the plot to place a marker before marking."
            mark_btn_disabled = True
        elif last_mark is None:
            warning_msg = "No previous mark set."
            mark_btn_disabled = True
        else:
            try:
                interval = float(marker) - float(last_mark)
            except Exception:
                warning_msg = "Error calculating marked interval."
                mark_btn_disabled = True
            else:
                if interval <= 0 or interval < 1.0:
                    warning_msg = "Marked interval must be at least 1 second."
                    mark_btn_disabled = True

        if not mark_btn_disabled:
            if not user_name or not user_name.strip():
                warning_msg = "Enter your User Name before marking."
                mark_btn_disabled = True
            elif not interp:
                warning_msg = "Choose Interpretable or Non-Interpretable."
                mark_btn_disabled = True
            elif interp == "No":
                if not comment or not comment.strip():
                    warning_msg = "Comment required for Non-Interpretable interval."
                    mark_btn_disabled = True
            elif interp == "Yes":
                if not ca:
                    warning_msg = "Select Cardiac Arrest status."
                    mark_btn_disabled = True
                elif ca == "Yes":
                    if not cpr:
                        warning_msg = "Select CPR status."
                        mark_btn_disabled = True
                elif ca == "No":
                    if not rhythm:
                        warning_msg = "Select Rhythm Label."
                        mark_btn_disabled = True
                    elif rhythm in ["Unable to Determine", "Other"] and (not rex or not rex.strip()):
                        warning_msg = "Explanation required for selected rhythm."
                        mark_btn_disabled = True

        self.mark_warning.setText(warning_msg)
        self.mark_btn.setDisabled(mark_btn_disabled)

    def make_plot_click_handler(self, lead_idx):
        def handler(mouse_event):
            if mouse_event.button() != Qt.LeftButton:
                return
            vb = self.waveform_plots[lead_idx].getViewBox()
            mouse_point = vb.mapSceneToView(mouse_event.scenePos())
            t_clicked = float(mouse_point.x())
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
                "user": self.username_input.text(),
                "subject": self.subject_dropdown.currentData(),
                "interp": self.get_interp_val(),
                "comment": self.comment_box.toPlainText(),
                "ca": self.get_ca_val(),
                "cpr": self.get_cpr_val(),
                "rhythm_label": self.rhythm_dropdown.currentText() if self.rhythm_dropdown.isEnabled() else "",
                "rhythm_expl": self.rhythm_explanation.toPlainText(),
                "start": self.last_mark,
                "end": self.current_marker,
            }
            print(f"APPENDING ANNOTATION: {ann}")
            self.annotations.append(ann)

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
            # Adjust these keys/fields to match your annotation dict!
            user = ann.get("user", "")
            subject = ann.get("subject", "")
            interp = ann.get("interp", "")
            cardiac_arrest = ann.get("ca", "")
            cpr = ann.get("cpr", "")
            rhythm = ann.get("rhythm_label", "")
            noninterp_expl = ann.get("comment", "")
            rhythm_expl = ann.get("rhythm_expl", "")
            start = ann.get("start", "")
            end = ann.get("end", "")

            row_data = [
                user, subject, interp, cardiac_arrest, cpr, rhythm,
                noninterp_expl, rhythm_expl, str(start), str(end)
            ]
            for col, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                self.ann_table.setItem(idx, col, item)

    # def update_waveform_and_mark(self):
    #     data_store = self.data_store
    #     annotations = getattr(self, "annotations", [])
    #     window_size = float(self.win_size.value())
    #     x_scroll_val = float(self.x_scrollbar.value())
    #     marker = getattr(self, "current_marker", None)
    #     last_mark = getattr(self, "last_mark", 0.0)
    #     user_name = self.username_input.text()
    #     subject_selected = self.subject_dropdown.currentData()
    #     interpretability = self.get_interp_val()
    #     cardiac_arrest = self.get_ca_val()
    #     cpr_status = self.get_cpr_val()
    #     rhythm_label = self.rhythm_dropdown.currentText()
    #     comment_box = self.comment_box.toPlainText()
    #     rhythm_explanation = self.rhythm_explanation.toPlainText()
    #     n_mark = getattr(self, "n_mark_clicks", 0)

    #     # Data load/empty state
    #     if not data_store or "time" not in data_store or not data_store["time"]:
    #         for plot in self.waveform_plots:
    #             plot.clear()
    #             plot.setTitle("No Data Loaded")
    #         self.set_scrollbar_range(0, 100, 0)
    #         self.annotations = []
    #         return

    #     # times = np.array(data_store["time"])
    #     # time_axis = times[0]   # Use first lead's time axis
    #     # # time_relative = times - times[0] if len(times) > 0 else times
    #     # time_relative = time_axis - time_axis[0]
    #     # leads = [np.array(l) for l in data_store["leads"]]
    #     # lead_names = data_store["lead_names"]

    #     # --- Marking/Annotation Append logic ---
    #     if getattr(self, "triggered_by_mark_btn", False):
    #         can_save = True
    #         try:
    #             start = float(last_mark)
    #             end = float(marker)
    #             can_save = (
    #                 marker is not None and
    #                 end > start and
    #                 (end - start) >= 1.0 and
    #                 user_name and user_name.strip() and
    #                 interpretability in ("Yes", "No") and
    #                 (interpretability != "No" or (comment_box and comment_box.strip()))
    #             )
    #         except Exception:
    #             can_save = False

    #         if can_save:
    #             annotation = {
    #                 "user_name": user_name,
    #                 "subject": subject_selected,
    #                 "interpretable": interpretability,
    #                 "cardiac_arrest": cardiac_arrest if interpretability == "Yes" else None,
    #                 "cpr_status": cpr_status if interpretability == "Yes" and cardiac_arrest == "Yes" else None,
    #                 "rhythm_label": rhythm_label if interpretability == "Yes" and cardiac_arrest == "No" else None,
    #                 "noninterp_explanation": comment_box,
    #                 "rhythm_explanation": rhythm_explanation,
    #                 "start": start,
    #                 "end": end
    #             }
    #             annotations = annotations + [annotation]
    #             last_mark = end
    #             marker = None
    #             self.annotations = annotations
    #             self.last_mark = last_mark
    #             self.current_marker = marker
    #             self.update_table_data()

    #     times = np.array(data_store["time"])
    #     if len(times.shape) == 2:
    #         time_axis = times[0]
    #     else:
    #         time_axis = times  # Already 1D
    #     time_relative = time_axis - time_axis[0]
    #     t_min, t_max = float(time_relative[0]), float(time_relative[-1])

    #     # Use leads as list-of-1D numpy arrays:
    #     leads = [np.array(l) for l in data_store["leads"]]
    #     lead_names = data_store["lead_names"]

    #     t_min, t_max = float(time_relative[0]), float(time_relative[-1])
    #     x_scroll_min = t_min
    #     x_scroll_max = max(t_max - window_size, t_min)
    #     x_scroll_val = np.clip(x_scroll_val, x_scroll_min, x_scroll_max)
    #     left = x_scroll_val
    #     right = min(x_scroll_val + window_size, t_max)

    #     Fs = 240.0
    #     desired_fs = 80.0
    #     stride = int(np.floor(Fs / desired_fs))
    #     stride = max(stride, 1)

    #     # --- Plotting Section ---
    #     for i, (plot, sig, name) in enumerate(zip(self.waveform_plots, leads, lead_names)):
    #         plot.clear()
    #         plot.setTitle(name)
    #         plot.scene().sigMouseClicked.connect(self.make_plot_click_handler(i))
    #         # --- Ensure signal is 1D ---
    #         sig = np.asarray(sig)
    #         if sig.ndim == 2:
    #             print(f"Lead {i}: signal has shape {sig.shape} (should be 1D) -- using first row/col")
    #             if sig.shape[0] == 1:
    #                 sig = sig[0]
    #             elif sig.shape[1] == 1:
    #                 sig = sig[:,0]
    #             else:
    #                 sig = sig[i]  # fallback: try ith signal (matches time axis)
    #         assert sig.ndim == 1, f"sig after reshape is {sig.shape}"
    #         # --- Index times for window ---
    #         plot_times = time_axis - time_axis[0]
    #         idx = (plot_times >= left) & (plot_times <= right)
    #         if np.sum(idx) == 0:
    #             continue  # Nothing in window
    #         ds_times = plot_times[idx][::stride]
    #         ds_sig = sig[idx][::stride]
    #         print(f"Lead {i}: times {ds_times.shape} sig {ds_sig.shape}")
    #         plot.plot(ds_times, ds_sig, pen='b', name=name)
    #         # Draw marker if present
    #         if marker is not None and left <= marker <= right:
    #             vline = pg.InfiniteLine(marker, angle=90, pen='r')
    #             plot.addItem(vline)
    #         # Add annotations (rect/vline)
    #         for ann in annotations:
    #             color = LABEL_COLORS.get(ann.get("rhythm_label", ""), DEFAULT_COLOR)
    #             start, end = ann["start"], ann["end"]
    #             if end < left or start > right:
    #                 continue
    #             rect = pg.LinearRegionItem([max(left, start), min(right, end)],
    #                                     brush=pg.mkBrush(color, 50), movable=False)
    #             plot.addItem(rect)
    #             vline = pg.InfiniteLine(end, angle=90, pen=pg.mkPen('k', style=pg.QtCore.Qt.DotLine))
    #             plot.addItem(vline)
    #         # plot.setXRange(left, right)
    #     self.waveform_plots[0].setXRange(left, right, padding=0)
    #     self.set_scrollbar_range(x_scroll_min, x_scroll_max, x_scroll_val)

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

        # ---- Optional: restrict scroll/zoom to X only ----
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

    # def update_table_data(self):
    #     annotations = getattr(self, "annotations", [])
    #     table = self.ann_table
    #     table.setRowCount(0)
    #     if not annotations:
    #         return
    #     table.setRowCount(len(annotations))
    #     for row, a in enumerate(annotations):
    #         fields = [
    #             a.get("user_name", ""),
    #             a.get("subject", ""),
    #             a.get("interpretable", ""),
    #             a.get("cardiac_arrest", ""),
    #             a.get("cpr_status", ""),
    #             a.get("rhythm_label", ""),
    #             a.get("noninterp_explanation", ""),
    #             a.get("rhythm_explanation", ""),
    #             f"{float(a.get('start', 0)):.2f}",
    #             f"{float(a.get('end', 0)):.2f}",
    #         ]
    #         for col, value in enumerate(fields):
    #             table.setItem(row, col, QTableWidgetItem(str(value)))

    def save_all_to_file(self):
        annotations = getattr(self, "annotations", [])
        subject = self.subject_dropdown.currentData()
        base_folder = getattr(self, "base_folder", None)
        if not annotations:
            self.save_message.setText("No annotations to save.")
            return
        if not subject or not base_folder:
            self.save_message.setText("Subject or base folder not set.")
            return

        subject_folder = os.path.join(base_folder, subject)
        output_folder = os.path.join(subject_folder, "output")
        os.makedirs(output_folder, exist_ok=True)
        now = datetime.now().strftime("%Y%m%d")
        filename = f"annotations_{subject}_{now}.csv"
        fullpath = os.path.join(output_folder, filename)
        pd.DataFrame(annotations).to_csv(fullpath, index=False)
        self.save_message.setText(f"Saved to {fullpath}")

    def autosave_annotations(self):
        annotations = getattr(self, "annotations", [])
        subject = self.subject_dropdown.currentData()
        base_folder = getattr(self, "base_folder", None)
        if not annotations or not subject or not base_folder:
            return
        subject_folder = os.path.join(base_folder, subject)
        output_folder = os.path.join(subject_folder, "output")
        os.makedirs(output_folder, exist_ok=True)
        filename = f"annotations_{subject}.csv"
        fullpath = os.path.join(output_folder, filename)
        pd.DataFrame(annotations).to_csv(fullpath, index=False)
        self.save_message.setText(f"Autoaved to {fullpath}")

    # --- Utility slots for GUI logic that you will implement: ---
    def get_interp_val(self):
        if self.radio_interp_yes.isChecked():
            return "Yes"
        if self.radio_interp_no.isChecked():
            return "No"
        return None

    def get_ca_val(self):
        if self.cardiac_arrest_yes.isChecked():
            return "Yes"
        if self.cardiac_arrest_no.isChecked():
            return "No"
        return None

    def get_cpr_val(self):
        if self.cpr_yes.isChecked():
            return "Yes"
        if self.cpr_no.isChecked():
            return "No"
        return None
    
    def clear_cardiac_arrest(self):
        self.cardiac_arrest_yes.setAutoExclusive(False)
        self.cardiac_arrest_no.setAutoExclusive(False)
        self.cardiac_arrest_yes.setChecked(False)
        self.cardiac_arrest_no.setChecked(False)
        self.cardiac_arrest_yes.setAutoExclusive(True)
        self.cardiac_arrest_no.setAutoExclusive(True)

    def clear_cpr(self):
        self.cpr_yes.setAutoExclusive(False)
        self.cpr_no.setAutoExclusive(False)
        self.cpr_yes.setChecked(False)
        self.cpr_no.setChecked(False)
        self.cpr_yes.setAutoExclusive(True)
        self.cpr_no.setAutoExclusive(True)

# ---- Example connections (in __init__): -----
# self.set_folder_btn.clicked.connect(self.set_base_folder)
# self.load_subject_btn.clicked.connect(self.load_subject_data)
# self.save_all_btn.clicked.connect(self.save_all_to_file)
# self.waveform_plot_* / all fields: connect value/changed signals to update_sidebar_ui as needed
# Call update_waveform_and_mark() on window/scrollbar/plot click, etc.
# Call update_table_data() when annotations change

# ---- Subclass or Mixin pattern -----
# class MainApp(QMainWindow, AnnotationAppCallbacks): ...