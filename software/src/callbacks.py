from dash import Output, Input, State, callback_context, no_update
from plotly.subplots import make_subplots
import plotly.graph_objs as go
from processing import list_subjects, load_waveforms_for_subject
import numpy as np
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
        times, leads, lead_names, units = load_waveforms_for_subject(base_folder, subject_name)
        # Find Subset of Time to pull for display (max point holder for time range)
        max_points = 20000
        times_ds = times[:max_points]
        leads_ds = [(l[:max_points] if l is not None else None) for l in leads]
        return {
            "time": times_ds.tolist(),   # always as a list!
            "leads": [l.tolist() if l is not None else None for l in leads_ds],
            "lead_names": lead_names,
            "subject": subject_name,
        }

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
        State("comments", "value"),
        State("rhythm-label", "value"),
        State("cpr-status", "value"),
        State("shockable", "value"),
        State("onset-event", "value"),
        prevent_initial_call=False,
    )
    def update_waveform_and_mark(
        data_store,
        annotations,
        window_size,
        x_scroll_val,
        click_data,
        n_mark,
        current_marker,
        last_mark,
        user_name,
        subject_selected,
        interpretability,
        comments,
        rhythm_label,
        cpr_status,
        shockable,
        onset_event,
        
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
        leads = [np.array(l) for l in data_store["leads"]]
        lead_names = data_store["lead_names"]
        t_min, t_max = float(times[0]), float(times[-1])
        window_size = float(window_size or 10)
        x_scroll_min = t_min
        x_scroll_max = max(t_max - window_size, t_min)
        x_scroll_val = float(x_scroll_val if x_scroll_val is not None else t_min)
        x_scroll_val = min(max(x_scroll_val, x_scroll_min), x_scroll_max)

        # Handle plot click to set/move marker
        if trigger == 'waveform-graph' and click_data and 'points' in click_data:
            marker = float(click_data['points'][0]['x'])

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
                elif not interpretability:
                    warning = "Choose Interpretable or Non-Interpretable"
                elif (interpretability == "Non-Interpretable") and (not comments or not comments.strip()):
                    warning = "Comment required for Non-Interpretable interval"
                elif not rhythm_label:
                    warning = "Select Rhythm Label"
                elif not cpr_status:
                    warning = "Select CPR status"
                elif not shockable:
                    warning = "Select Shockable status"
                elif not onset_event:
                    warning = "Select onset event"
                else:
                    annotation = {
                        "user_name": user_name,  
                        "subject": subject_selected,
                        "interpretable": interpretability,
                        "comments": comments or "",
                        "rhythm_label": rhythm_label,
                        "cpr_status": cpr_status,
                        "shockable": shockable,
                        "onset_event": onset_event,
                        "start": start,
                        "end": end,
                    }
                    annotations = annotations + [annotation]
                    last_mark = end
                    marker = None  # Remove marker after marking

        # --- Disable Logic for Mark Button ---
        mark_disabled = (
        marker is None or
        (float(marker) <= float(last_mark)) or
        (float(marker) - float(last_mark)) < 1.0 or
        not interpretability or
        not rhythm_label or
        not cpr_status or
        not shockable or
        not onset_event or
        (interpretability == "Non-Interpretable" and (not comments or not comments.strip()))
        )
        # Reason message if button is disabled and not from an explicit Mark error
        if marker is None:
            why_disabled = "Click on the plot to place a marker before marking."
        elif float(marker) <= float(last_mark) or (float(marker) - float(last_mark)) < 1.0:
            why_disabled = "Marked interval must be at least 1 second."
        elif not interpretability:
            why_disabled = "Choose Interpretable or Non-Interpretable."
        elif not rhythm_label:
            why_disabled = "Select Rhythm Label."
        elif not cpr_status:
            why_disabled = "Select CPR status."
        elif not shockable:
            why_disabled = "Select Shockable status."
        elif not onset_event:
            why_disabled = "Select Onset Event."
        elif interpretability == "Non-Interpretable" and (not comments or not comments.strip()):
            why_disabled = "Comment required for Non-Interpretable interval."
        else:
            why_disabled = ""

        # Use validation warning if available, otherwise show why_disabled if button is disabled
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
        for i, (sig, name) in enumerate(zip(leads, lead_names)):
            # Plot the full data!
            fig.add_trace(
                go.Scatter(x=times, y=sig, mode='lines', name=name),
                row=i+1, col=1
            )
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
            mark_disabled  
        )



    # @app.callback(
    # Output('waveform-graph', 'figure'),
    # Output('x-scrollbar', 'min'),
    # Output('x-scrollbar', 'max'),
    # Output('x-scrollbar', 'value'),
    # Output('current_marker', 'data'),
    # Output('last_mark', 'data'),
    # Output('annotations-list', 'data'),
    # Output('mark-warning', 'children'),
    # Output('mark-btn', 'disabled'),
    # # MAIN input: data-store triggers on subject load
    # Input('data-store', 'data'),  
    # Input('plot-btn', 'n_clicks'),
    # # Secondary: annotation/controls/window
    # Input('annotations-list', 'data'),
    # Input('view-window-size', 'value'),
    # Input('x-scrollbar', 'value'),
    # Input('waveform-graph', 'clickData'),
    # Input('mark-btn', 'n_clicks'),
    # # States: things you only need to fetch
    # State('subject-dropdown', 'value'),
    # State('current_marker', 'data'),
    # State('last_mark', 'data'),
    # State('user-name', 'value'),
    # State("interpretability", "value"),
    # State("comments", "value"),
    # State("rhythm-label", "value"),
    # State("cpr-status", "value"),
    # State("shockable", "value"),
    # State("onset-event", "value"),
    # prevent_initial_call=False,
    # )
    # def update_waveform_and_mark(
    #     data_store,
    #     n_clicks,
    #     annotations,
    #     window_size,
    #     x_scroll_val,
    #     click_data,
    #     n_mark,
    #     subject_selected,
    #     current_marker,
    #     last_mark,
    #     user_name,
    #     interpretability,
    #     comments,
    #     rhythm_label,
    #     cpr_status,
    #     shockable,
    #     onset_event,
    # ):
    #     ctx = callback_context
    #     print(f"\n=== CALLBACK TRIGGERED: ctx.triggered={ctx.triggered} ===")

    #     warning = ""
    #     marker = current_marker
    #     annotations = annotations or []
    #     last_mark = float(last_mark) if last_mark is not None else 0.0

    #     if not data_store or "time" not in data_store or not data_store["time"]:
    #         print("DEBUG: No Data Loaded")
    #         fig = go.Figure(layout={"height": 400, "title": "No Data Loaded"})
    #         return fig, 0, 100, 0, marker, last_mark, annotations, warning, True

    #     times = np.array(data_store["time"])
    #     leads = [np.array(l) if l is not None else None for l in data_store["leads"]]
    #     lead_names = data_store["lead_names"]
    #     t_min, t_max = float(times[0]), float(times[-1])
    #     window_size = float(window_size or 10)
    #     x_scroll_min = t_min
    #     x_scroll_max = max(t_max - window_size, t_min)
    #     x_scroll_val = float(x_scroll_val if x_scroll_val is not None else t_min)
    #     x_scroll_val = min(max(x_scroll_val, x_scroll_min), x_scroll_max)

    #     print(f"times: {len(times)} pts, leads: {[len(l) if l is not None else 'None' for l in leads]}")
    #     max_plot_points = 2000

    #     # Handle marker positioning
    #     if ctx.triggered and ctx.triggered[0]['prop_id'].split('.')[0] == 'waveform-graph' and click_data and 'points' in click_data:
    #         marker = float(click_data['points'][0]['x'])
    #         print(f"Marker set to {marker}")

    #     # --- Marking logic & validation (omitted for brevity) ---
    #     if ctx.triggered == 'mark-btn' and n_mark:
    #         if marker is None:
    #             warning = "Click on the plot to place a marker before marking."
    #         else:
    #             start = float(last_mark)
    #             end = float(marker)
    #             # Enforce direction and interval
    #             if end <= start or (end - start) < 1.0:
    #                 warning = "Marked interval must be at least 1 second."
    #             elif not interpretability:
    #                 warning = "Choose Interpretable or Non-Interpretable"
    #             elif (interpretability == "Non-Interpretable") and (not comments or not comments.strip()):
    #                 warning = "Comment required for Non-Interpretable interval"
    #             elif not rhythm_label:
    #                 warning = "Select Rhythm Label"
    #             elif not cpr_status:
    #                 warning = "Select CPR status"
    #             elif not shockable:
    #                 warning = "Select Shockable status"
    #             elif not onset_event:
    #                 warning = "Select onset event"
    #             else:
    #                 annotation = {
    #                     "user_name": user_name,  
    #                     "subject": subject_selected,
    #                     "interpretable": interpretability,
    #                     "comments": comments or "",
    #                     "rhythm_label": rhythm_label,
    #                     "cpr_status": cpr_status,
    #                     "shockable": shockable,
    #                     "onset_event": onset_event,
    #                     "start": start,
    #                     "end": end,
    #                 }
    #                 annotations = annotations + [annotation]
    #                 last_mark = end
    #                 marker = None  # Remove marker after marking

    #     # --- Disable Logic for Mark Button ---
    #     mark_disabled = (
    #     marker is None or
    #     (float(marker) <= float(last_mark)) or
    #     (float(marker) - float(last_mark)) < 1.0 or
    #     not interpretability or
    #     not rhythm_label or
    #     not cpr_status or
    #     not shockable or
    #     not onset_event or
    #     (interpretability == "Non-Interpretable" and (not comments or not comments.strip()))
    #     )
    #     # Reason message if button is disabled and not from an explicit Mark error
    #     if marker is None:
    #         why_disabled = "Click on the plot to place a marker before marking."
    #     elif float(marker) <= float(last_mark) or (float(marker) - float(last_mark)) < 1.0:
    #         why_disabled = "Marked interval must be at least 1 second."
    #     elif not interpretability:
    #         why_disabled = "Choose Interpretable or Non-Interpretable."
    #     elif not rhythm_label:
    #         why_disabled = "Select Rhythm Label."
    #     elif not cpr_status:
    #         why_disabled = "Select CPR status."
    #     elif not shockable:
    #         why_disabled = "Select Shockable status."
    #     elif not onset_event:
    #         why_disabled = "Select Onset Event."
    #     elif interpretability == "Non-Interpretable" and (not comments or not comments.strip()):
    #         why_disabled = "Comment required for Non-Interpretable interval."
    #     else:
    #         why_disabled = ""

    #     # Use validation warning if available, otherwise show why_disabled if button is disabled
    #     if not warning and mark_disabled:
    #         warning = why_disabled

    #     # --- Plotting ---
    #     left = x_scroll_val
    #     right = min(x_scroll_val + window_size, t_max)
    #     n_lead = len(lead_names)
    #     fig = make_subplots(
    #         rows=n_lead, cols=1, shared_xaxes=True,
    #         vertical_spacing=0.03, subplot_titles=lead_names
    #     )
    #     for i, (sig, name) in enumerate(zip(leads, lead_names)):
    #         row_idx = i + 1
    #         print(f"\n--- Plot Row {row_idx}/{n_lead} {name} ---")
    #         if sig is not None and len(sig) and len(times):
    #             sig_arr = np.array(sig)
    #             time_arr = np.array(times)
    #             min_len = min(len(sig_arr), len(time_arr))
    #             sig_arr = sig_arr[:min_len]
    #             time_arr = time_arr[:min_len]
    #             mask = (time_arr >= left) & (time_arr <= right)
    #             win_times = time_arr[mask]
    #             win_signal = sig_arr[mask]
    #             win_len = len(win_signal)
    #             print(f"{name}: window len={win_len}")

    #             # # Downsample visible window for fast interactive plot
    #             # if win_len > max_plot_points:
    #             #     idx = np.linspace(0, win_len - 1, max_plot_points).astype(int)
    #             #     plot_times = win_times[idx]
    #             #     plot_signal = win_signal[idx]
    #             #     print(f"{name}: downsampled to {len(plot_times)} pts")
    #             # else:
    #             #     plot_times = win_times
    #             #     plot_signal = win_signal
    #             #     print(f"{name}: {len(plot_times)} pts, no downsample")

    #             if len(sig):
    #                 y_min, y_max = np.min(sig), np.max(sig)
    #                 y_pad = 0.03 * (y_max - y_min) if y_max > y_min else 1
    #                 fig.add_trace(
    #                     go.Scatter(
    #                         x=time_arr,
    #                         y=sig,
    #                         mode="lines",
    #                         name=name,
    #                         line=dict(width=1)
    #                     ),
    #                     row=row_idx, col=1
    #                 )
    #                 fig.update_yaxes(range=[y_min - y_pad, y_max + y_pad], row=row_idx, col=1)
    #             else:
    #                 print(f"{name}: nothing in window, displaying missing text")
    #                 fig.add_trace(
    #                     go.Scatter(x=[], y=[], mode='lines', name=f"Missing {name}"),
    #                     row=row_idx, col=1
    #                 )
    #                 fig.add_annotation(
    #                     text=f"Missing {name}", xref=f"x{row_idx}", yref=f"y{row_idx}",
    #                     x=0.5 * (left + right), y=0, xanchor="center", yanchor="middle",
    #                     font=dict(color="gray", size=14), showarrow=False, row=row_idx, col=1
    #                 )
    #         else:
    #             print(f"{name}: MISSING")
    #             fig.add_trace(
    #                 go.Scatter(x=[], y=[], mode='lines', name=f"Missing {name}"),
    #                 row=row_idx, col=1
    #             )
    #             fig.add_annotation(
    #                 text=f"Missing {name}", xref=f"x{row_idx}", yref=f"y{row_idx}",
    #                 x=0.5 * (left + right), y=0, xanchor="center", yanchor="middle",
    #                 font=dict(color="gray", size=14), showarrow=False, row=row_idx, col=1
    #             )
    #         fig.update_yaxes(showgrid=True, zeroline=True, row=row_idx, col=1)

    #     fig.update_xaxes(range=[left, right], title="Time (s)")
    #     fig.update_layout(
    #         height=120 * n_lead + 80,
    #         margin={'l': 55, 'r': 11, 't': 38, 'b': 38},
    #         showlegend=False,
    #         dragmode="pan"
    #     )
    #     print("=== END OF PLOTTING DEBUG ===")
    #     return (
    #         fig,
    #         x_scroll_min,
    #         x_scroll_max,
    #         x_scroll_val,
    #         marker,
    #         last_mark,
    #         annotations,
    #         warning,
    #         mark_disabled
    #     )

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