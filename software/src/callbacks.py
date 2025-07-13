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
        Input('waveform-graph', 'id'),
        prevent_initial_call=False
    )
    def subject_dropdown_cb(_):
        options = [{"label": s, "value": s} for s in list_subjects()]
        value = options[0]["value"] if options else None
        return options, value

    @app.callback(
        Output('current_time', 'data'),
        Output('last_mark', 'data'),
        Output('annotations-list', 'data'),
        Output('mark-btn', 'disabled'),
        Output('prev-second-btn', 'disabled'),
        Output('next-second-btn', 'disabled'),
        Output('mark-warning', 'children'),
        Output('data-store', 'data'),
        Output('waveform-length', 'data'),
        Input('subject-dropdown', 'value'),
        Input('prev-second-btn', 'n_clicks'),
        Input('next-second-btn', 'n_clicks'),
        Input('waveform-graph', 'relayoutData'),
        Input('mark-btn', 'n_clicks'),
        State('current_time', 'data'),
        State('last_mark', 'data'),
        State('waveform-length', 'data'),
        State('annotations-list', 'data'),
        # New: all form elements!
        State("interpretability", "value"),
        State("comments", "value"),
        State("rhythm-label", "value"),
        State("cpr-status", "value"),
        State("shockable", "value"),
        State("onset-event", "value"),
        State('data-store', 'data'),
        prevent_initial_call=True
    )
    def nav_mark_scroll_load(subject_selected, n_prev, n_next, relayout, n_mark,
                             current_time, last_mark, waveform_length, annotations,
                             interpretability, comments, rhythm_label, cpr_status, shockable, onset_event, data_store):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

        # SUBJECT CHANGE
        if trigger == "subject-dropdown":
            if not subject_selected:
                return 1, 0, [], True, True, True, "", {}, None
            times, signals, lead_names = load_all_leads(subject_selected)
            data_store = {
                "time": times.tolist(),
                "leads": [s.tolist() for s in signals],
                "lead_names": lead_names,
            }
            waveform_length = int(times[-1])
            current_time = 1
            last_mark = 0
            annotations = []
            return current_time, last_mark, annotations, True, True, False if waveform_length > 1 else True, "", data_store, waveform_length

        # Parse current states
        current_time = int(current_time) if current_time is not None else 1
        last_mark = int(last_mark) if last_mark is not None else 0
        waveform_length = int(waveform_length) if waveform_length is not None else 0
        annotations = annotations or []

        # NAVIGATION
        if trigger in ['next-second-btn', 'prev-second-btn']:
            delta = 1 if trigger == 'next-second-btn' else -1
            min_nav = max(last_mark + 1, 1)
            max_nav = waveform_length
            current_time = min(max(current_time + delta, min_nav), max_nav)

        # PLOT SCROLL
        elif trigger == 'waveform-graph':
            if relayout and "xaxis.range[0]" in relayout and "xaxis.range[1]" in relayout:
                x_left = relayout["xaxis.range[0]"]
                x_right = relayout["xaxis.range[1]"]
                mid = (x_left + x_right) / 2
                min_nav = max(last_mark + 1, 1)
                max_nav = waveform_length
                snap = int(np.clip(np.round(mid), min_nav, max_nav))
                current_time = snap

        # MARKING
        warning = ""
        mark_disabled = False

        if trigger == "mark-btn":
            # Validation
            if not interpretability:
                warning = "Choose Interpretable or Non-Interpretable"
                mark_disabled = True
            elif (interpretability == "Non-Interpretable") and (not comments or not comments.strip()):
                warning = "Comment required for Non-Interpretable interval"
                mark_disabled = True
            elif not rhythm_label:
                warning = "Select Rhythm Label"
                mark_disabled = True
            elif not cpr_status:
                warning = "Select CPR status"
                mark_disabled = True
            elif not shockable:
                warning = "Select Shockable status"
                mark_disabled = True
            elif not onset_event:
                warning = "Select onset event"
                mark_disabled = True
            else:
                # All fields valid, record annotation
                start = last_mark
                end = current_time
                if end > start:
                    annotation = {
                        "interpretable": interpretability,
                        "comments": comments or "",
                        "rhythm_label": rhythm_label,
                        "cpr_status": cpr_status,
                        "shockable": shockable,
                        "onset_event": onset_event,
                        "start": float(start),
                        "end": float(end)
                    }
                    annotations = annotations + [annotation]
                    last_mark = end
                    current_time = min(last_mark + 1, waveform_length)
        # Check disables after nav/mark
        mark_disabled = (
            (current_time <= last_mark) or (current_time > waveform_length)
            or not interpretability or not rhythm_label or not cpr_status or not shockable or not onset_event
            or (interpretability == "Non-Interpretable" and (not comments or not comments.strip()))
        )
        prev_disabled = (current_time <= max(last_mark + 1, 1))
        next_disabled = (current_time >= waveform_length)

        return current_time, last_mark, annotations, mark_disabled, prev_disabled, next_disabled, warning, no_update, no_update

    @app.callback(
        Output('waveform-graph', 'figure'),
        Output('annotations-table', 'data'),
        Input('data-store', 'data'),
        Input('current_time', 'data'),
        Input('annotations-list', 'data'),
        Input('waveform-length', 'data'),
        prevent_initial_call=False
    )
    def update_waveform_plot(data_store, current_time, annotations, waveform_length):
        if not data_store or "time" not in data_store or not data_store["time"]:
            return go.Figure(layout={"height": 400, "title": "No Data Loaded"}), []
        times = np.array(data_store["time"])
        leads = [np.array(l) for l in data_store["leads"]]
        lead_names = data_store["lead_names"]
        n_lead = len(lead_names)
        current_time = int(current_time) if current_time is not None else 1
        left = current_time - WINDOW_PADDING
        right = current_time + WINDOW_PADDING
        t_min, t_max = times[0], times[-1]
        fig = make_subplots(
            rows=n_lead, cols=1, shared_xaxes=True,
            vertical_spacing=0.03, subplot_titles=lead_names
        )
        for i, (sig, name) in enumerate(zip(leads, lead_names)):
            fig.add_trace(
                go.Scatter(x=times, y=sig, mode='lines', name=name, line=dict(color=PLOTLY_COLORS[i % len(PLOTLY_COLORS)])),
                row=i+1, col=1
            )
            fig.update_yaxes(title_text=name, row=i+1, col=1)
        for row in range(1, n_lead+1):
            fig.add_vline(x=current_time, line_color="red", line_width=2, row=row, col=1)
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
            if left < t_min:
                fig.add_vrect(x0=left, x1=t_min, fillcolor="gray", opacity=0.13, line_width=0, layer="below", row=row, col=1)
            if right > t_max:
                fig.add_vrect(x0=t_max, x1=right, fillcolor="gray", opacity=0.13, line_width=0, layer="below", row=row, col=1)
        fig.update_xaxes(range=[left, right], title="Time (s)")
        fig.update_layout(
            height=120 * n_lead + 80, margin={'l': 55, 'r': 11, 't': 38, 'b': 38},
            showlegend=False, dragmode="pan"
        )
        table_data = [
            {**a, "start": float(a["start"]), "end": float(a["end"])}
            for a in (annotations or [])
        ]
        return fig, table_data

    @app.callback(
        Output('save-message', 'children'),
        Input('save-all-btn', 'n_clicks'),
        State('annotations-list', 'data'),
        State('subject-dropdown', 'value'),
        prevent_initial_call=True
    )
    def save_all_to_file(n_clicks, annotations, subject):
        import pandas as pd
        import os
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