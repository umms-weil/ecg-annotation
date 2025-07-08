from dash import Dash, dcc, html, dash_table
from callbacks import register_callbacks
from processing import DATA_ROOT
import os

# Define the absolute path to assets
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_PATH = os.path.join(PROJECT_ROOT, "assets")

app = Dash(__name__,  assets_folder=ASSETS_PATH)

app.layout = html.Div([
    # The sidebar -- now with id for CSS control (no position/fixed set here)
    html.Div([
        html.H2("Annotations"),
        html.Label("Select Subject:"),
        dcc.Dropdown(
            id='subject-dropdown',
            options=[],    # will be populated via callback
            value=None,
            placeholder="Choose a subject",
            style={'marginBottom': '12px'}
        ),
        html.Label("Select lead for annotation:"),
        dcc.Dropdown(
            id='lead-dropdown',
            options=[],
            value=None,
            placeholder="Pick a lead below.",
            style={'marginBottom': '12px'}
        ),
        html.Label("Label:"),
        dcc.Dropdown(
            id='label-dropdown',
            options=[{"label": l, "value": l} for l in ["Test", "Noise", "Artifact", "Other"]],
            value='Test',
            clearable=False,
            style={'marginBottom': '12px'}
        ),
        html.Button('Start', id='start-btn', n_clicks=0, style={'width': '100%', 'marginBottom': '6px'}),
        html.Button('Stop', id='stop-btn', n_clicks=0, style={'width': '100%', 'marginBottom': '6px'}),
        html.Button('Reset', id='reset-btn', n_clicks=0, style={'width': '100%', 'marginBottom': '6px'}),
        html.Button('Save Annotation', id='save-btn', n_clicks=0, disabled=True, style={'width': '100%', 'marginBottom':'10px'}),
        html.Hr(),
        html.Div(id='instructions', style={"marginTop": "1em", "marginBottom":"0.7em"}),
        html.H4("All annotations:"),
        dash_table.DataTable(
            id='annotations-table',
            columns=[
                {"name": "Remove", "id": "remove", "presentation": "markdown"},
                {"name": "Lead", "id": "lead"},
                {"name": "Label", "id": "label"},
                {"name": "Start", "id": "start"},
                {"name": "End", "id": "end"}
            ],
            data=[],
            style_cell={'textAlign': 'center', 'fontSize': 13},
            style_table={'height': 200, 'overflowY': 'auto'},
            row_deletable=False,
            editable=False
        ),
        html.Button("Save All Annotations", id="save-all-btn", n_clicks=0, style={'width': '100%', 'margin':'12px 0'}),
        html.Div(id='save-message', style={'color':'#156e13', 'fontWeight':'bold', 'fontSize':'13px', 'height':'16px'}),
        html.Div(id='last-annotation', style={'fontWeight': 'bold', 'color': 'green', 'fontSize': '13px'}),
    ], id='sidebar'),  # <--- IMPORTANT, id for CSS

    # The main content area (plots etc.) -- set marginLeft or padding to leave room for sidebar
    html.Div([
        html.Div([
            html.H4("All Leads Overview"),
            dcc.Graph(
                id='overview-graph',
                config={'displayModeBar': True},
                style={'height': '550px', 'marginBottom': '8px'}
            ),
        ]),
        html.Div([
            html.H4("Detail - 10 Second Window", style={'marginTop': '6px'}),
            html.Div([
                html.Button('Prev Window', id='prev-window-btn', n_clicks=0, style={'marginRight':'6px'}),
                html.Button('Next Window', id='next-window-btn', n_clicks=0)
            ], style={'marginBottom': '4px'}),
            dcc.Graph(
                id='detail-graph',
                config={'displayModeBar': True},
                style={'height': '350px', 'marginBottom':'2px'}
            ),
        ])
    ], style={
        'flexGrow': 1,
        'padding': '6px 10px 6px 10px',
        'marginLeft': '295px', 
    })
],
style={'display': 'flex'}
)

app.layout.children += [
    dcc.Store(id='data-store', data={}),
    dcc.Store(id='window-state', data={'start_time': 0.0}),
    dcc.Store(id='annotation-single', data={'mode': None, 'start': None, 'stop': None}),
    dcc.Store(id='annotations-list', data=[]),
]

register_callbacks(app)

if __name__ == '__main__':
    app.run(debug=True)