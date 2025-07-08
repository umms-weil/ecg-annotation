from dash import Output, Input, State, callback_context
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from processing import load_all_leads, list_subjects
import pandas as pd
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(PROJECT_ROOT, "data")
ASSETS_ROOT = os.path.join(PROJECT_ROOT, "assets")

WINDOW_SIZE = 10
EXTRA_SECONDS = 3

PLOTLY_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
]
LABEL_COLORS = {
    "Test": "LightGreen",
    "Noise": "LightPink",
    "Artifact": "Khaki",
    "Other": "LightSkyBlue",
}
DEFAULT_COLOR = "LightGray"

def register_callbacks(app):

    @app.callback(
        Output('subject-dropdown', 'options'),
        Output('subject-dropdown', 'value'),
        Input('subject-dropdown', 'options'),
        prevent_initial_call=False
    )
    def subject_dropdown_cb(_):
        subjects = list_subjects(DATA_ROOT)
        options = [{"label": s, "value": s} for s in subjects]
        value = options[0]["value"] if options else None
        return options, value

    @app.callback(
        Output('overview-graph', 'figure'),
        Output('data-store', 'data'),
        Output('lead-dropdown', 'options'),
        Input('subject-dropdown', 'value'),   # Now reacts to subject change
        Input('overview-graph', 'relayoutData'),
        State('window-state', 'data'),
        State('annotations-list', 'data'),
        State('lead-dropdown', 'value'),
        State('detail-graph', 'relayoutData'),
        prevent_initial_call=False
    )
    def show_multilead_fig(subject_selected, _, window_state, annotations_list, lead_idx, detail_relayout):
        if not subject_selected:
            fig = go.Figure()
            fig.update_layout(title="No Subject Selected", height=400)
            return fig, {}, []
        subject_path = os.path.join(DATA_ROOT, subject_selected)
        times, signals, lead_names = load_all_leads(subject_path)
        n_lead = len(signals)
        w0 = (window_state.get('start_time', 0) if window_state else 0)
        selected_lead = lead_idx if lead_idx is not None else 0

        fig = make_subplots(
            rows=n_lead,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            subplot_titles=lead_names
        )
        for i, (sig, name) in enumerate(zip(signals, lead_names), 1):
            fig.add_trace(
                go.Scatter(x=times, y=sig, mode='lines', name=name, line=dict(color=PLOTLY_COLORS[(i-1)%len(PLOTLY_COLORS)]), showlegend=False),
                row=i, col=1
            )
            fig.update_yaxes(title_text=name, row=i, col=1)

        focus_row = int(selected_lead)
        x0 = max(w0-EXTRA_SECONDS, 0)
        x1 = min(w0+WINDOW_SIZE+EXTRA_SECONDS, times[-1]) if len(times) else 0
        if len(signals) > 0 and 0 <= focus_row < len(signals):
            fig.add_vrect(
                x0=x0, x1=x1,
                fillcolor="LightSkyBlue", opacity=0.12,
                line_width=0, layer="below",
                row=focus_row+1, col=1
            )

        for ann in annotations_list or []:
            this_row = lead_names.index(ann["lead"]) + 1 if ann["lead"] in lead_names else None
            if this_row is not None:
                fig.add_vrect(
                    x0=ann['start'],
                    x1=ann['end'],
                    fillcolor=LABEL_COLORS.get(ann['label'], DEFAULT_COLOR),
                    opacity=0.18,
                    layer="below",
                    line_width=0,
                    row=this_row, col=1
                )
        fig.update_layout(
            height=90 * n_lead + 60,
            margin={'l': 45, 'r': 10, 't': 32, 'b': 30}
        )
        data_store = {
            "time": times.tolist(),
            "leads": [s.tolist() for s in signals],
            "lead_names": lead_names,
        }
        lead_dropdown_options = [{"label": name, "value": i} for i, name in enumerate(lead_names)]
        return fig, data_store, lead_dropdown_options

    def make_table_data(annotations):
        table = []
        for i, a in enumerate(annotations):
            row = {**a, "start": f"{a['start']:.2f}", "end": f"{a['end']:.2f}"}
            row["remove"] = "❌"
            table.append(row)
        return table

    @app.callback(
        Output('detail-graph', 'figure'),
        Output('window-state', 'data'),
        Output('instructions', 'children'),
        Output('save-btn', 'disabled'),
        Output('annotation-single', 'data'),
        Output('annotations-list', 'data'),
        Output('annotations-table', 'data'),
        Output('lead-dropdown', 'value'),
        Input('subject-dropdown', 'value'),
        Input('lead-dropdown', 'value'),
        Input('next-window-btn', 'n_clicks'),
        Input('prev-window-btn', 'n_clicks'),
        Input('start-btn', 'n_clicks'),
        Input('stop-btn', 'n_clicks'),
        Input('detail-graph', 'clickData'),
        Input('reset-btn', 'n_clicks'),
        Input('save-btn', 'n_clicks'),
        Input('annotations-table', 'active_cell'),
        Input('overview-graph', 'clickData'),
        State('window-state', 'data'),
        State('data-store', 'data'),
        State('annotation-single', 'data'),
        State('annotations-list', 'data'),
        State('label-dropdown', 'value'),
        State('annotations-table', 'data'),
        prevent_initial_call=False
    )
    def detail_and_annotate(
        subject_selected, lead_idx, next_n, prev_n, n_start, n_stop, detail_click, n_reset, n_save, active_cell, overview_click,
        window_state, data_store, annotation_single, annotations_list, label, table_data
    ):
        instr = "1. Click 'Start', then click plot; 2. Click 'Stop', then click for END."
        disabled = True
        annotation_single = annotation_single or {'mode': None, 'start': None, 'stop': None}
        annotations_list = annotations_list or []
        window_state = window_state or {'start_time': 0}
        data_store = data_store or {"time": [], "leads": [], "lead_names": []}
        t = data_store.get("time", [])
        leads = data_store.get("leads", [])
        lead_names = data_store.get("lead_names", [])

        new_dropdown_val = int(lead_idx) if lead_idx is not None else 0

        w0 = window_state.get('start_time', 0.0)
        n_lead = len(leads)
        t_arr = t
        total_duration = t_arr[-1] if len(t_arr) > 0 else 0
        trig = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else None

        if not leads or new_dropdown_val is None or int(new_dropdown_val) < 0 or int(new_dropdown_val) >= len(leads):
            fig = go.Figure()
            fig.update_layout(title="No Data", height=350)
            return fig, window_state, "Please select a lead.", True, annotation_single, annotations_list, [], 0

        if trig == "subject-dropdown":
            # Clear annotation and reset window on subject change
            annotation_single = {'mode': None, 'start': None, 'stop': None}
            annotations_list = []
            window_state = {'start_time': 0}
            # Reset to first lead of new subject
            new_dropdown_val = 0
            w0 = 0.0

        # 1. Jump to window and lead on overview click
        if trig == "overview-graph" and overview_click is not None:
            x_click = overview_click["points"][0]["x"]
            curve_idx = overview_click["points"][0]["curveNumber"]
            w0 = max(0, min(x_click - WINDOW_SIZE/2, total_duration - WINDOW_SIZE))
            new_dropdown_val = curve_idx

        # 2. Navigation
        if trig == 'next-window-btn' and len(t_arr) > 0:
            max_start = max(0, total_duration - WINDOW_SIZE)
            w0 = min(w0 + WINDOW_SIZE, max_start)
        elif trig == 'prev-window-btn' and len(t_arr) > 0:
            w0 = max(0.0, w0 - WINDOW_SIZE)

        focus_left = max(w0-EXTRA_SECONDS, 0)
        focus_right = min(w0+WINDOW_SIZE+EXTRA_SECONDS, total_duration)

        signal = leads[int(new_dropdown_val)]
        color_this_lead = PLOTLY_COLORS[int(new_dropdown_val)%len(PLOTLY_COLORS)]
        lead_name = lead_names[int(new_dropdown_val)]

        if trig == 'start-btn':
            annotation_single['mode'] = 'start'
            instr = "Click in detail plot to place START pin for label."
        elif trig == 'stop-btn':
            annotation_single['mode'] = 'stop'
            instr = "Click in detail plot to place STOP pin for label."
        elif trig == "detail-graph" and detail_click and len(t_arr) > 0:
            x_click = float(detail_click['points'][0]['x'])
            if annotation_single['mode'] == 'start' and focus_left <= x_click <= focus_right:
                annotation_single['start'] = x_click
                annotation_single['mode'] = None
                instr = "Start placed. Click 'Stop', then plot for END pin."
            elif annotation_single['mode'] == 'stop' and focus_left <= x_click <= focus_right:
                annotation_single['stop'] = x_click
                annotation_single['mode'] = None
                instr = "Stop placed. Click 'Save Annotation' to record."
        elif trig == 'reset-btn':
            annotation_single = {'mode': None, 'start': None, 'stop': None}
            instr = "Annotation reset. 1. Click 'Start', then click; 2. Click 'Stop', then click."
        # Save annotation
        if trig == 'save-btn' and annotation_single.get('start') is not None and annotation_single.get('stop') is not None:
            start = annotation_single['start']
            stop = annotation_single['stop']
            ann = {
                'lead': lead_name,
                'label': label,
                'start': float(min(start, stop)),
                'end': float(max(start, stop)),
            }
            annotations_list = annotations_list + [ann]
            annotation_single = {'mode': None, 'start': None, 'stop': None}
            instr = "Annotation saved! Start a new annotation as needed."
        if annotation_single.get('start') is not None and annotation_single.get('stop') is not None and annotation_single.get('mode') is None:
            disabled = False
        # Remove annotation
        if trig == "annotations-table" and active_cell and active_cell['column_id'] == "remove":
            idx_to_remove = active_cell['row']
            if 0 <= idx_to_remove < len(annotations_list):
                annotations_list = [a for i, a in enumerate(annotations_list) if i != idx_to_remove]
        table = make_table_data(annotations_list)
        plot_left = focus_left
        plot_right = focus_right
        mask = [v is not None and plot_left <= v < plot_right for v in t_arr]
        t_win = [tx for tx, m in zip(t_arr, mask) if m]
        s_win = [sx for sx, m in zip(signal, mask) if m]
        fig = go.Figure()
        if len(t_win) > 0:
            fig.add_trace(go.Scatter(
                x=t_win, y=s_win, mode='lines', name=lead_name,
                line=dict(color=color_this_lead)
            ))
            fig.update_layout(
                title=f"{lead_name}, focus: {w0:.2f}-{w0+WINDOW_SIZE:.2f}s",
                height=350,
                xaxis={'title': 'Time (s)', 'range': [plot_left, plot_right]},
                yaxis={'title': 'Amplitude (a.u.)'},
                margin={'l': 30, 'r': 10, 't': 32, 'b': 36},
                dragmode='pan',
                shapes=[
                    dict(type="rect",
                        xref="x", yref="paper",
                        x0=w0, x1=w0+WINDOW_SIZE, y0=0, y1=1,
                        fillcolor="LightSkyBlue", opacity=0.13, line_width=0, layer="below"
                    )
                ]
            )
            for ann in annotations_list:
                if ann['lead'] == lead_name:
                    if ann['end'] >= plot_left and ann['start'] <= plot_right:
                        color = LABEL_COLORS.get(ann["label"], DEFAULT_COLOR)
                        fig.add_vrect(
                            x0=max(ann['start'], plot_left),
                            x1=min(ann['end'], plot_right),
                            fillcolor=color,
                            opacity=0.32,
                            layer="below",
                            line_width=0,
                        )
                        fig.add_vline(x=ann['start'], line_color="blue", opacity=0.7, line_dash="dot")
                        fig.add_vline(x=ann['end'], line_color="red", opacity=0.7, line_dash="dot")
            if annotation_single.get('start') is not None and plot_left <= annotation_single['start'] <= plot_right:
                fig.add_vline(x=annotation_single['start'], line_color="blue", line_dash="dash",
                              annotation_text="Start", annotation_position="top")
            if annotation_single.get('stop') is not None and plot_left <= annotation_single['stop'] <= plot_right:
                fig.add_vline(x=annotation_single['stop'], line_color="red", line_dash="dash",
                              annotation_text="Stop", annotation_position="top")
        else:
            fig.update_layout(title="No Data", height=350)
        return fig, {'start_time': w0}, instr, disabled, annotation_single, annotations_list, table, new_dropdown_val

    @app.callback(
        Output('save-message', 'children'),
        Input('save-all-btn', 'n_clicks'),
        State('annotations-list', 'data'),
        State('subject-dropdown', 'value'),
        prevent_initial_call=True
    )
    def save_all_to_file(n_clicks, annotations, subject):
        if n_clicks:
            if not annotations:
                return "No annotations to save."
            os.makedirs("output", exist_ok=True)
            df = pd.DataFrame(annotations)
            if subject:
                outname = f"annotations_{subject}.csv"
            else:
                outname = "annotations.csv"
            fullpath = os.path.join("output", outname)
            df.to_csv(fullpath, index=False)
            return f"Saved to {fullpath}"
        return ""