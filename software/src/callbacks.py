from dash import Output, Input, State, callback_context, no_update
from plotly.subplots import make_subplots
import plotly.graph_objs as go
from processing import load_all_leads, list_subjects
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
        Output('subject-dropdown', 'options'),
        Output('subject-dropdown', 'value'),
        Input('waveform-graph', 'id'),  # do not change: UI triggers list update
        prevent_initial_call=False
    )
    def subject_dropdown_cb(_):
        options = [{"label": s, "value": s} for s in list_subjects()]
        value = options[0]["value"] if options else None
        return options, value

    @app.callback(
    Output('data-store', 'data'),
    Input('subject-dropdown', 'value'),
    prevent_initial_call=True
    )
    def load_subject_data(subject_selected):
        if not subject_selected:
            return {}
        times, signals, lead_names = load_all_leads(subject_selected)
        return {
            "time": times.tolist(),
            "leads": [s.tolist() for s in signals],
            "lead_names": lead_names,
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