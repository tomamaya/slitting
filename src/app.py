import dash
from dash import dcc, html, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
from scipy.optimize import linprog
import base64
import io
from flask import send_from_directory



# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server

# Define paths for default files
DEFAULT_COILS_PATH = 'inventory.xlsx'
DEFAULT_ORDERS_PATH = 'order.xlsx'

# Define the layout of the app
app.layout = html.Div([
    html.H1("Slit planner optimization (Beta version)"),
    
    # Instructions for uploading files
    html.Div([
        html.P("Step 1: Upload the Inventory File. In case no file, download the below test file"),
        
        dcc.Upload(
            id='upload-coils',
            children=html.Button('Upload Coils File'),
            multiple=False
        ),
        
        html.P("Step 2: Upload the Orders File. In case no file, download the below test file"),
        
        dcc.Upload(
            id='upload-orders',
            children=html.Button('Upload Orders File'),
            multiple=False
        ),
    ], style={'margin-bottom': '20px'}),
    
    # Download links for default files
    html.Div([
        html.A("Download Default Coils File", id="download-coils-link", href="/download/inventory.xlsx", download="inventory.xlsx"),
        html.Br(),
        html.A("Download Default Orders File", id="download-orders-link", href="/download/order.xlsx", download="order.xlsx"),
    ], style={'margin-bottom': '20px'}),
    
    # Instructions for running optimization
    html.P("Step 3: Press the below button to run the plan optimization", style={'margin-bottom': '20px'}),
    
    # Run Optimization button
    html.Button('Run Optimization', id='run-button', n_clicks=0),
    
    # Output containers
    html.Div(id='upload-status'),
    html.Div(id='patterns-output')
])

# Define the knapsack problem
def knapsack(weights, values, capacity):
    n = len(weights)
    c = [-v for v in values]  # Objective function (minimization problem)
    A_ub = [weights]
    b_ub = [capacity]
    bounds = [(0, 1) for _ in range(n)]  # Items are either in or out (0 or 1)

    # Solve the knapsack problem
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')
    if result.success:
        return -result.fun, result.x
    else:
        raise ValueError("Optimization failed")

# Define the function to optimize slitting patterns
def optimize_slitting_patterns(coils, orders):
    patterns = []
    for coil in coils:
        coil_width, coil_length = coil
        widths = [order[0] for order in orders]
        lengths = [order[1] for order in orders]
        values = lengths  # The value is the length to satisfy
        weights = widths   # The weight is the width of the order
        capacity = coil_width
        
        # Solve the knapsack problem
        value, x = knapsack(weights, values, capacity)
        pattern = [widths[i] for i in range(len(x)) if x[i] > 0.5]
        patterns.append((coil, pattern))
    
    return patterns

# Define the function to minimize shear adjustments
def minimize_shear_adjustments(patterns):
    adjusted_patterns = []
    for pattern in patterns:
        coil, cuts = pattern
        sorted_cuts = sorted(cuts)
        adjusted_patterns.append((coil, sorted_cuts))
    
    return adjusted_patterns

# Define callback to process uploaded files and run optimization
@app.callback(
    Output('upload-status', 'children'),
    Output('patterns-output', 'children'),
    Input('upload-coils', 'contents'),
    Input('upload-orders', 'contents'),
    State('upload-coils', 'filename'),
    State('upload-orders', 'filename'),
    Input('run-button', 'n_clicks')
)
def update_output(coils_file, orders_file, coils_filename, orders_filename, n_clicks):
    if n_clicks == 0:
        raise PreventUpdate

    if not (coils_file and orders_file):
        raise PreventUpdate

    try:
        # Decode the uploaded files
        content_type, content_string = coils_file.split(',')
        coils_df = pd.read_excel(io.BytesIO(base64.b64decode(content_string)))
        
        content_type, content_string = orders_file.split(',')
        orders_df = pd.read_excel(io.BytesIO(base64.b64decode(content_string)))
        
        # Convert DataFrame to list of tuples
        coils = list(coils_df.itertuples(index=False, name=None))
        orders = list(orders_df.itertuples(index=False, name=None))
        
        patterns = optimize_slitting_patterns(coils, orders)
        adjusted_patterns = minimize_shear_adjustments(patterns)
        
        def format_pattern(pattern):
            return ' '.join(map(str, pattern))
        
        patterns_output = html.Div([
            html.H2("Patterns Before Shear Adjustment"),
            html.Table(
                [html.Tr([html.Th("Coil (Width(mm), Length(mm)"), html.Th("Pattern")])] +
                [html.Tr([html.Td(str(pattern[0])), html.Td(format_pattern(pattern[1]))]) for pattern in patterns]
            ),
            html.H2("Patterns After Shear Adjustment"),
            html.Table(
                [html.Tr([html.Th("Coil (Width(mm), Length(mm)"), html.Th("Pattern")])] +
                [html.Tr([html.Td(str(pattern[0])), html.Td(format_pattern(pattern[1]))]) for pattern in adjusted_patterns]
            )
        ])
        
        return "Files successfully uploaded and processed.", patterns_output

    except Exception as e:
        return f"An error occurred: {e}", ""

# Route to serve static files
@app.server.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory('.', filename, as_attachment=True)

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)
