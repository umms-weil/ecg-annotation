from dash import Output, Input, State, callback_context, no_update
from plotly.subplots import make_subplots
import plotly.graph_objs as go
from processing import list_subjects, load_waveforms_for_subject, get_code_time_bounds
import numpy as np
import pandas as pd
import os


WINDOW_PADDING = 6
PLOTLY_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
]
LABEL_COLORS = {
    "Normal Heart Rhythm": "LightGreen",
    "Sinus tachycardia": "LightBlue",
    "Bradycardia": "Khaki",
    "Supraventricular tachycardia": "Tomato",
    "Atrial Flutter": "Lavender",
    "Atrial Fibrillation": "SlateGray",
    "Ventricular Tachycardia": "Orange",
    "Ventricular Fibrillation": "Red",
    "Atrial Pacing Rhythm": "Gold",
    "Ventricular Pacing Rhythm": "Teal",
    "Idioventricular Rhythm": "Purple"
}
DEFAULT_COLOR = "LightGray"

def register_callbacks(app):

    @app.callback(
    Output('base-folder-store', 'data'),
    Output('base-folder-status', 'children'),
    Input('set-folder-btn', 'n_clicks'),
    State('base-folder-input', 'value')
    )
    def set_base_folder(n_clicks, folder_path):
        print("SET FOLDER CLICKED", folder_path)
        if not folder_path or not os.path.isdir(folder_path):
            return "", "❌ Invalid folder."
        return folder_path, f"📂 Base folder set: {folder_path}"

    @app.callback(
    Output('subject-dropdown', 'options'),
    Output('subject-dropdown', 'disabled'),
    Input('base-folder-store', 'data'),
    prevent_initial_call=True
    )
    def update_subject_dropdown(base_folder):
        if not base_folder or not os.path.isdir(base_folder):
            return [], True
        # Get subject info
        subjects = list_subjects(base_folder)
        options = []
        for subj in subjects:
            if subj["has_annotations"]:
                label = f"✅ {subj['name']} ({subj['n_annotations']} annots)"
            else:
                label = f"⭕ {subj['name']} (0 annots)"
            options.append({"label": label, "value": subj["name"]})
        return options, False

    @app.callback(
    Output('data-store', 'data'),
    Input('load-subject-btn', 'n_clicks'),
    State('subject-dropdown', 'value'),
    State('base-folder-store', 'data'),
    prevent_initial_call=True
    )
    def load_subject_data(n_clicks, subject_name, base_folder):
        print(f"Button clicked: load subject {subject_name} from {base_folder}")
        if not subject_name or not base_folder or not os.path.isdir(base_folder):
            return {}
        # code_csv_path = base_folder + '/waveform_manifest.csv'
        # TODO: Remove the hard path
        # code_csv_path = '/nfs/turbo/umms-sardara/projects/cpr_afib_prediction/data/pre-raw/2023_05_10_cpr_waveforms/waveform_manifest.csv'
        code_csv_path = '/home/pwalczyk/projects/ecg-annotation/software/data/waveform_manifest.csv'
        recording_start_sec, code_start_sec, code_stop_sec = get_code_time_bounds(subject_name, code_csv_path)
        times_ds, leads_ds, lead_names, units = load_waveforms_for_subject(
            base_folder, subject_name,
            recording_start_sec=recording_start_sec,
            code_start_sec=code_start_sec,
            code_stop_sec=code_stop_sec,
            desired_waveforms=["I", "II", "III", "V", "AVF", "AVL", "AVR"]
        )
        return {
            "time": times_ds.tolist() if hasattr(times_ds, "tolist") else list(times_ds),
            "leads": [l.tolist() if l is not None else None for l in leads_ds],
            "lead_names": lead_names,
            "subject": subject_name,
        }

    @app.callback(
    Output('comment-box', 'disabled'),
    Output('cpr-status', 'options'),
    Output('rhythm-label', 'disabled'),
    Output('rhythm-explanation', 'disabled'),
    Input("interpretability", "value"),
    Input("cardiac-arrest", "value"),
    Input("rhythm-label", "value"),
    )
    def control_disables(interpretability, cardiac_arrest, rhythm_label):
        # Defaults
        comment_disabled = True        
        cpr_disabled = True
        rhythm_disabled = True
        rhythm_explanation_disabled = True

        if interpretability == "No":
            comment_disabled = False
            cpr_disabled = True
            rhythm_disabled = True
            rhythm_explanation_disabled = True
        elif interpretability == "Yes":
            comment_disabled = True
            if cardiac_arrest == "Yes":
                cpr_disabled = False
                rhythm_disabled = True
                rhythm_explanation_disabled = True
            elif cardiac_arrest == "No":
                cpr_disabled = True
                rhythm_disabled = False
                rhythm_explanation_disabled = not (rhythm_label in ["Unable to Determine", "Other"])
            else:
                cpr_disabled = True
                rhythm_disabled = True
                rhythm_explanation_disabled = True

        cpr_options = [
            {"label": "Yes", "value": "Yes", "disabled": cpr_disabled},
            {"label": "No", "value": "No", "disabled": cpr_disabled}
        ]
        return comment_disabled, cpr_options, rhythm_disabled, rhythm_explanation_disabled

    @app.callback(
        Output('waveform-graph', 'figure'),
        Output('x-scrollbar', 'min'),
        Output('x-scrollbar', 'max'),
        Output('x-scrollbar', 'value'),
        Output('current_marker', 'data'),
        Output('last_mark', 'data'),
        Output('annotations-list', 'data'),
        Output('mark-warning', 'children'),
        Output('mark-btn', 'disabled'),
        Input('data-store', 'data'),
        Input('annotations-list', 'data'),
        Input('view-window-size', 'value'),
        Input('x-scrollbar', 'value'),
        Input('waveform-graph', 'clickData'),
        Input('mark-btn', 'n_clicks'),
        State('current_marker', 'data'),
        State('last_mark', 'data'),
        State('user-name', 'value'),
        State('subject-dropdown', 'value'),
        State("interpretability", "value"),
        State("cardiac-arrest", "value"),
        State("cpr-status", "value"),
        State("rhythm-label", "value"),
        State("comment-box", "value"),
        State("rhythm-explanation", "value"),
        prevent_initial_call=False,
    )
    def update_waveform_and_mark(
        data_store, annotations, window_size, x_scroll_val, click_data, n_mark,
        current_marker, last_mark, user_name, subject_selected,
        interpretability, cardiac_arrest, cpr_status, rhythm_label,
        comment_box, rhythm_explanation,
    ):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        warning = ""
        marker = current_marker
        annotations = annotations or []
        last_mark = float(last_mark) if last_mark is not None else 0.0

        # Data load/empty state
        if not data_store or "time" not in data_store or not data_store["time"]:
            fig = go.Figure(layout={"height": 400, "title": "No Data Loaded"})
            return fig, 0, 100, 0, marker, last_mark, annotations, warning, True

        # Get waveform/time data
        times = np.array(data_store["time"])
        # Relative Time
        time_relative = times[0] - times[0][0]
        leads = [np.array(l) for l in data_store["leads"]]
        lead_names = data_store["lead_names"]
        t_min, t_max = float(time_relative[0]), float(time_relative[-1])
        window_size = float(window_size or 10)
        x_scroll_min = t_min
        x_scroll_max = max(t_max - window_size, t_min)
        x_scroll_val = float(x_scroll_val if x_scroll_val is not None else t_min)
        x_scroll_val = min(max(x_scroll_val, x_scroll_min), x_scroll_max)

        # Handle plot click to set/move marker
        if trigger == 'waveform-graph' and click_data and 'points' in click_data:
            marker = float(click_data['points'][0]['x'])
            # Center window on marker, but don't exceed bounds
            left = min(max(marker - window_size/2, t_min), t_max - window_size)
            left = max(left, t_min)  # Ensure not off the left edge
            x_scroll_val = left

        comment_disabled = True
        cpr_disabled = True
        rhythm_disabled = True
        rhythm_explanation_disabled = True

        if interpretability == "No":
            comment_disabled = False
            cpr_disabled = True
            rhythm_disabled = True
            rhythm_explanation_disabled = True
        elif interpretability == "Yes":
            comment_disabled = True
            if cardiac_arrest == "Yes":
                cpr_disabled = False
                rhythm_disabled = True
                rhythm_explanation_disabled = True
            elif cardiac_arrest == "No":
                cpr_disabled = True
                rhythm_disabled = False
                rhythm_explanation_disabled = not (rhythm_label in ["Unable to Determine", "Other"])
            else:
                cpr_disabled = True
                rhythm_disabled = True
                rhythm_explanation_disabled = True

        # --- FORCIBLY CLEAR values for disabled fields! ---
        if comment_disabled:
            comment_box = None
        if cpr_disabled:
            cpr_status = None
        if rhythm_disabled:
            rhythm_label = None
        if rhythm_explanation_disabled:
            rhythm_explanation = None

        # --- Marking and Validation ---
        if trigger == 'mark-btn' and n_mark:
            if marker is None:
                warning = "Click on the plot to place a marker before marking."
            else:
                start = float(last_mark)
                end = float(marker)
                # Enforce direction and interval
                if end <= start or (end - start) < 1.0:
                    warning = "Marked interval must be at least 1 second."
                # Validation only for ENABLED fields
                elif not interpretability:
                    warning = "Choose Interpretable or Non-Interpretable"
                elif interpretability == "No":
                    if comment_box is None or not comment_box.strip():
                        warning = "Comment required for Non-Interpretable interval"
                    else:
                        # Only comment required; all other (disabled) fields already set to None
                        annotation = {
                            "user_name": user_name,
                            "subject": subject_selected,
                            "interpretable": interpretability,
                            "cardiac_arrest": None,
                            "cpr_status": None,
                            "rhythm_label": None,
                            "noninterp_explanation": comment_box,
                            "rhythm_explanation": None,
                            "start": start,
                            "end": end,
                        }
                        annotations = annotations + [annotation]
                        last_mark = end
                        marker = None
                elif interpretability == "Yes":
                    if not cardiac_arrest:
                        warning = "Select Cardiac Arrest status"
                    elif cardiac_arrest == "Yes":
                        if not cpr_status:
                            warning = "Select CPR status"
                        else:
                            # Only CPR present, rest are None
                            annotation = {
                                "user_name": user_name,
                                "subject": subject_selected,
                                "interpretable": interpretability,
                                "cardiac_arrest": cardiac_arrest,
                                "cpr_status": cpr_status,
                                "rhythm_label": None,
                                "noninterp_explanation": None,
                                "rhythm_explanation": None,
                                "start": start,
                                "end": end,
                            }
                            annotations = annotations + [annotation]
                            last_mark = end
                            marker = None
                    elif cardiac_arrest == "No":
                        if not rhythm_label:
                            warning = "Select Rhythm Label"
                        elif rhythm_label in ["Unable to Determine", "Other"] and (rhythm_explanation is None or not rhythm_explanation.strip()):
                            warning = "Explanation required for selected rhythm"
                        else:
                            # Rhythm and possibly explanation present, rest None
                            annotation = {
                                "user_name": user_name,
                                "subject": subject_selected,
                                "interpretable": interpretability,
                                "cardiac_arrest": cardiac_arrest,
                                "cpr_status": None,
                                "rhythm_label": rhythm_label,
                                "noninterp_explanation": None,
                                "rhythm_explanation": rhythm_explanation if rhythm_label in ["Unable to Determine", "Other"] else None,
                                "start": start,
                                "end": end,
                            }
                            annotations = annotations + [annotation]
                            last_mark = end
                            marker = None

        # --- Disable Logic for Mark Button ---
        mark_disabled = False
        why_disabled = ""
        if marker is None:
            mark_disabled = True
            why_disabled = "Click on the plot to place a marker before marking."
        elif float(marker) <= float(last_mark) or (float(marker) - float(last_mark)) < 1.0:
            mark_disabled = True
            why_disabled = "Marked interval must be at least 1 second."
        elif not interpretability:
            mark_disabled = True
            why_disabled = "Choose Interpretable or Non-Interpretable"
        elif interpretability == "No":
            if comment_box is None or not comment_box.strip():
                mark_disabled = True
                why_disabled = "Comment required for Non-Interpretable interval"
        elif interpretability == "Yes":
            if not cardiac_arrest:
                mark_disabled = True
                why_disabled = "Select Cardiac Arrest status"
            elif cardiac_arrest == "Yes":
                if not cpr_status:
                    mark_disabled = True
                    why_disabled = "Select CPR status"
            elif cardiac_arrest == "No":
                if not rhythm_label:
                    mark_disabled = True
                    why_disabled = "Select Rhythm Label"
                elif rhythm_label in ["Unable to Determine", "Other"] and (rhythm_explanation is None or not rhythm_explanation.strip()):
                    mark_disabled = True
                    why_disabled = "Explanation required for selected rhythm"

        if not warning and mark_disabled:
            warning = why_disabled

        # --- Plotting ---
        left = x_scroll_val
        right = min(x_scroll_val + window_size, t_max)
        n_lead = len(lead_names)
        fig = make_subplots(
            rows=n_lead, cols=1, shared_xaxes=True,
            vertical_spacing=0.03, subplot_titles=lead_names
        )
        for i, (sig, name, ts) in enumerate(zip(leads, lead_names, times)):
            if sig is not None and len(sig) > 0 and ts is not None and len(ts) > 0:
                plot_times = ts - ts[0]
                # ---- Downsample ----
                Fs = 240.0
                desired_fs = 100.0
                stride = int(np.floor(Fs / desired_fs))
                stride = max(stride, 1)
                ds_times = plot_times[::stride]
                ds_sig = sig[::stride]
                # ---- Plotting Trace ----
                print(f'Plotting trace {i}')
                fig.add_trace(
                    go.Scatter(x=ds_times, y=ds_sig, mode='lines', name=name),
                    row=i+1, col=1
                )
                fig.update_yaxes(autorange=True, row=i+1, col=1)
            else:
                print(f'Skipping trace {i} (no data)')
            fig.update_yaxes(autorange=True, row=i+1, col=1)
        # Only set the initial and slider-update X mode:
        fig.update_xaxes(range=[left, right], title="Time (s)")
        if marker is not None and left <= marker <= right:
            for row in range(1, n_lead+1):
                fig.add_vline(x=marker, line_color="red", line_width=2, row=row, col=1)
        # Annotation intervals
        for row in range(1, n_lead+1):
            for ann in annotations or []:
                color = LABEL_COLORS.get(ann["rhythm_label"], DEFAULT_COLOR)
                fig.add_vrect(
                    x0=ann["start"], x1=ann["end"],
                    fillcolor=color, opacity=0.18, line_width=0,
                    annotation_text=ann.get("rhythm_label", ""),
                    annotation_position="top right",
                    row=row, col=1
                )
                # Add dotted color-coded vline at mark endpoint
                fig.add_vline(
                    x=ann["end"], line_color='black', line_dash="dot", line_width=2, row=row, col=1
                )
        fig.update_xaxes(range=[left, right], title="Time (s)")
        fig.update_layout(
            height=120 * n_lead + 80, margin={'l': 55, 'r': 11, 't': 38, 'b': 38},
            showlegend=False, dragmode="pan"
        )
        return (
            fig,
            x_scroll_min,
            x_scroll_max,
            x_scroll_val,
            marker,
            last_mark,
            annotations,
            warning,
            False  
        )

    @app.callback(
    Output('annotations-table', 'data'),
    Input('annotations-list', 'data')
    )
    def update_table_data(annotations):
        if not annotations:
            return []
        # If any of your annotation fields are floats, you may want to format as needed
        return [
            {**a, "start": float(a["start"]), "end": float(a["end"])}
            for a in annotations
        ]

    @app.callback(
        Output('save-message', 'children'),
        Input('save-all-btn', 'n_clicks'),
        State('annotations-list', 'data'),
        State('subject-dropdown', 'value'),
        prevent_initial_call=True
    )
    def save_all_to_file(n_clicks, annotations, subject):
        import pandas as pd
        from datetime import datetime
        if n_clicks:
            if not annotations:
                return "No annotations to save."
            os.makedirs("output", exist_ok=True)
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"annotations_{subject}_{now}.csv" if subject else f"annotations_{now}.csv"
            fullpath = os.path.join("output", filename)
            pd.DataFrame(annotations).to_csv(fullpath, index=False)
            return f"Saved to {fullpath}"
        return ""