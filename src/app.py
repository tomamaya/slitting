import dash
from dash import dcc, html, Input, Output, State
from dash.exceptions import PreventUpdate
import pandas as pd
from scipy.optimize import linprog
import base64
import io
import plotly.graph_objects as go
import plotly.express as px

# Initialize the Dash app
app = dash.Dash(__name__)
server = app.server

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
        html.A("Download Default Coils File", id="download-coils-link", href="/assets/inventory.xlsx", download="inventory.xlsx"),
        html.Br(),
        html.A("Download Default Orders File", id="download-orders-link", href="/assets/order.xlsx", download="order.xlsx"),
    ], style={'margin-bottom': '20px'}),
    
    # Instructions for running optimization
    html.P("Step 3: Press the below button to run the plan optimization", style={'margin-bottom': '20px'}),
    
    # Run Optimization button
    html.Button('Run Optimization', id='run-button', n_clicks=0),
    
    # Output containers
    html.Div(id='upload-status'),
    html.Div(id='patterns-output'),
    
    # Graph controls
    html.Div([
        html.Label('Select Patterns Range:'),
        dcc.Slider(
            id='pattern-slider',
            min=0,
            max=0,  # Updated in callback
            value=0,
            marks={i: str(i) for i in range(0, 101, 10)},  # Default marks
            step=1
        ),
        html.Label('Adjust Bar Width:'),
        dcc.Slider(
            id='bar-width-slider',
            min=0.1,
            max=1.0,
            step=0.1,
            value=0.4
        ),
        html.Label('Adjust Bar Height:'),
        dcc.Slider(
            id='bar-height-slider',
            min=0.1,
            max=2.0,
            step=0.1,
            value=1.0
        )
    ], style={'margin-top': '20px'}),
    
    # Graph output
    dcc.Graph(id='patterns-graph')
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
    [Output('upload-status', 'children'),
     Output('patterns-output', 'children'),
     Output('patterns-graph', 'figure'),
     Output('pattern-slider', 'max'),
     Output('pattern-slider', 'value')],
    [Input('upload-coils', 'contents'),
     Input('upload-orders', 'contents'),
     Input('run-button', 'n_clicks'),
     Input('pattern-slider', 'value'),
     Input('bar-width-slider', 'value'),
     Input('bar-height-slider', 'value')],
    [State('upload-coils', 'filename'),
     State('upload-orders', 'filename')]
)
def update_output(coils_file, orders_file, n_clicks, selected_range, bar_width, bar_height, coils_filename, orders_filename):
    if n_clicks == 0:
        raise PreventUpdate

    if not (coils_file and orders_file):
        raise PreventUpdate

    try:
        # Function to decode and parse file contents
        def parse_file(contents):
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            return pd.read_excel(io.BytesIO(decoded))

        # Parse uploaded files directly
        coils_df = parse_file(coils_file)
        orders_df = parse_file(orders_file)
        
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

        # Update pattern slider max value
        pattern_slider_max = len(patterns) - 1
        pattern_slider_value = min(selected_range, pattern_slider_max)
        
        # Create the graph
        fig = go.Figure()
        color_scale = px.colors.qualitative.Plotly  # Use Plotly's qualitative color scale

        # Determine the patterns to display
        start_index = pattern_slider_value
        end_index = min(start_index + 10, len(patterns))
        patterns_to_display = patterns[start_index:end_index]

        for i, pattern in enumerate(patterns_to_display):
            pattern_widths = pattern[1]
            for j, width in enumerate(pattern_widths):
                fig.add_trace(go.Bar(
                    y=[f'Pattern {start_index + i + 1}'],
                    x=[width],
                    name=f'Width {width}',
                    marker_color=color_scale[j % len(color_scale)],
                    width=bar_width,  # Set the bar width
                    orientation='h',  # Horizontal bars
                    text=[f'{width}'],  # Display size inside the bar
                    textposition='inside'  # Place text inside the bars
                ))

        fig.update_layout(
            title='Sizes Within Each Pattern',
            xaxis_title='Width (mm)',
            yaxis_title='Pattern',
            barmode='stack',
            xaxis=dict(
                title='Width',
                tickmode='linear',
                tick0=0,
                dtick=5,  # Adjust as needed for scale-like behavior
                tickvals=[i for i in range(0, max(max(widths) for coil, widths in patterns) + 10, 5)],  # Set x-axis tick values
                ticktext=[str(i) for i in range(0, max(max(widths) for coil, widths in patterns) + 10, 5)]  # Set x-axis tick text
            ),
            yaxis=dict(
                title='Pattern',
                tickvals=[f'Pattern {i+1}' for i in range(len(patterns_to_display))],
                ticktext=[f'Pattern {i+1}' for i in range(len(patterns_to_display))]
            ),
            height=600 * bar_height  # Adjust height based on bar height
        )

        # Return the updated graph and other outputs
        return "Files successfully uploaded and processed.", patterns_output, fig, pattern_slider_max, pattern_slider_value

    except Exception as e:
        return f"An error occurred: {e}", "", go.Figure(), 0, 0  # Return an empty figure on error

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)