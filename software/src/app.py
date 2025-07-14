import dash
from dash import dcc, html, dash_table
from callbacks import register_callbacks

SIDEBAR_WIDTH = '230px'

app = dash.Dash(__name__)

app.layout = html.Div([
    html.Div([
        html.H3("Annotations", style={'fontSize': 17}),
        html.Label("User Name:", style={"fontWeight": "bold", 'fontSize': 11}),
        dcc.Input(id="user-name", placeholder="Enter user name...", type="text", value="", style={"marginBottom": 8, 'fontSize': 11, 'width': '100%'}),
        html.Label("Subject:", style={"fontWeight": "bold", 'fontSize': 11}),
        dcc.Dropdown(
            id='subject-dropdown',
            options=[],  # Populated by callback
            value=None,
            placeholder="Choose a subject",
            style={'marginBottom': '8px', 'fontSize': 11}
        ),
        html.Label("Interval is:", style={"fontWeight": "bold", "fontSize": 11}),
        dcc.RadioItems(
            id="interpretability",
            options=[{"label": "Interpretable", "value": "Interpretable"},
                     {"label": "Non-Interpretable", "value": "Non-Interpretable"}],
            value="Interpretable", inline=True, style={"fontSize": 11, 'marginBottom': '3px'}
        ),
        html.Label("Rhythm Label:", style={"fontWeight": "bold", "fontSize": 11}),
        dcc.RadioItems(
            id="rhythm-label",
            options=[
                {"label": "Normal Heart Rhythm", "value": "Normal Heart Rhythm"},
                {"label": "Sinus tachycardia", "value": "Sinus tachycardia"},
                {"label": "Bradycardia", "value": "Bradycardia"},
                {"label": "Supraventricular tachycardia", "value": "Supraventricular tachycardia"},
                {"label": "Atrial Flutter", "value": "Atrial Flutter"},
                {"label": "Atrial Fibrillation", "value": "Atrial Fibrillation"},
                {"label": "Ventricular Tachycardia", "value": "Ventricular Tachycardia"},
                {"label": "Ventricular Fibrillation", "value": "Ventricular Fibrillation"},
                {"label": "Atrial Pacing Rhythm", "value": "Atrial Pacing Rhythm"},
                {"label": "Ventricular Pacing Rhythm", "value": "Ventricular Pacing Rhythm"},
                {"label": "Idioventricular Rhythm", "value": "Idioventricular Rhythm"},
            ],
            value="Normal Heart Rhythm", inline=False, style={"fontSize": 10, 'marginBottom': '5px'}
        ),
        html.Label("CPR Status:", style={"fontWeight": "bold", "fontSize": 11}),
        dcc.RadioItems(
            id="cpr-status",
            options=[
                {"label": "Initiated", "value": "Initiated"},
                {"label": "Stopped", "value": "Stopped"},
                {"label": "Unable to Discern", "value": "Unable to Discern"}
            ], value="Initiated", inline=True, style={"fontSize": 11, 'marginBottom': '3px'}
        ),
        html.Label("Shockable?", style={"fontWeight": "bold", "fontSize": 11}),
        dcc.RadioItems(
            id="shockable",
            options=[
                {"label": "Shockable", "value": "Shockable"},
                {"label": "Non-Shockable", "value": "Non-Shockable"},
                {"label": "Unable to Discern", "value": "Unable to Discern"}
            ], value="Shockable", inline=True, style={"fontSize": 11, 'marginBottom': '3px'}
        ),
        html.Label("Onset Event:", style={"fontWeight": "bold", "fontSize": 11}),
        dcc.RadioItems(
            id="onset-event",
            options=[
                {"label": "None", "value": "None"},
                {"label": "Heart Rhythm", "value": "Heart Rhythm"},
                {"label": "Onset of Arrhythmia", "value": "Onset of Arrhythmia"},
                {"label": "CPR Initiating", "value": "CPR Initiating"},
                {"label": "CPR Termination", "value": "CPR Termination"},
            ], value="None", inline=True, style={"fontSize": 11, 'marginBottom': '5px'}
        ),
        html.Label("Comments/Explanation:", style={"fontWeight": "bold", 'fontSize': 11, 'marginBottom': '2px'}),
        dcc.Textarea(
            id="comments",
            placeholder="Add comment (required if Non-Interpretable)",
            style={'width': '100%', 'height': 24, "fontSize": 10, 'marginBottom': '5px'}
        ),
        html.Label("Navigation step size (seconds):", style={"fontWeight": "bold", 'fontSize': 11}),
        dcc.Input(
            id='nav-step-size', 
            type='number', 
            min=1, 
            value=1, 
            step=1, 
            style={'width': 60, 'fontSize': 11, 'marginBottom': '5px'}
        ),
        html.Div([
            html.Button('←', id='prev-second-btn', n_clicks=0, style={'width': '45%', 'marginRight': '5%'}),
            html.Button('→', id='next-second-btn', n_clicks=0, style={'width': '45%'})
        ], style={'marginBottom':'6px'}),
        html.Button('Mark', id='mark-btn', n_clicks=0, disabled=True, style={'width':'100%', 'marginBottom':'2px'}),
        html.Div(id='mark-warning', style={'color': 'red', 'fontWeight': 'bold', 'fontSize': 11, 'minHeight': '12px'}),
        html.Hr(),
        html.H5("Saved Annotations:", style={'margin':'2px 0', 'fontSize': 13}),
        dash_table.DataTable(
            id='annotations-table',
            columns=[
                {"name": "User", "id": "user_name"},
                {"name": "Subject", "id": "subject"},
                {"name": "Interpretable", "id": "interpretable"},
                {"name": "Rhythm", "id": "rhythm_label"},
                {"name": "CPR", "id": "cpr_status"},
                {"name": "Shockable", "id": "shockable"},
                {"name": "Onset", "id": "onset_event"},
                {"name": "Start", "id": "start"},
                {"name": "End", "id": "end"},
                {"name": "Comments", "id": "comments"},
            ],
            data=[],
            style_cell={'textAlign': 'center', 'fontSize': 10, 'padding': '1px 1px'},
            style_table={'height': 140, 'overflowY': 'auto', 'marginBottom':"7px", 'marginTop':"4px"},
            row_deletable=False,
            editable=False
        ),
        html.Button("Save All Annotations", id="save-all-btn", n_clicks=0, style={'width':'100%', 'margin':'7px 0 0 0'}),
        html.Div(id='save-message', style={'color':'#156e13', 'fontWeight':'bold', 'fontSize':'10px', 'height':'15px'}),
    ], id='sidebar', style={
        'width': SIDEBAR_WIDTH, 'minWidth': '100px', 'overflowY': 'auto',
        'padding': '8px 6px 7px 7px', 'background': '#F7F7F9',
        'boxSizing':'border-box', 'maxHeight': '98vh'
    }),

    html.Div([
        dcc.Graph(
            id='waveform-graph',
            config={'displayModeBar': True, 'scrollZoom': True, 'doubleClick': 'reset'},
            style={'height': '500px', 'marginBottom': '4px', 'maxWidth':'900px', 'width':'900px'}
        ),
    ], style={'flexGrow': 1, 'padding': '8px 8px 8px 10px', 'marginLeft': SIDEBAR_WIDTH})
], style={'display': 'flex', 'alignItems': 'flex-start', 'height':'100vh', 'background':'white'})

app.layout.children += [
    dcc.Store(id='data-store', data={}),
    dcc.Store(id='waveform-length', data=None),
    dcc.Store(id='annotations-list', data=[]),
    dcc.Store(id='current_time', data=1),
    dcc.Store(id='last_mark', data=0),
]

register_callbacks(app)

if __name__ == '__main__':
    app.run(debug=True,)