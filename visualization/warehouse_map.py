import plotly.graph_objects as go
from typing import List, Tuple
from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.routing import calculate_distance

def generate_detailed_path_points(pick_a: Pick, pick_b: Pick, warehouse: Warehouse) -> List[Tuple[float, float]]:
    """
    Generates the list of 2D coordinates representing the actual physical path
    a picker must take between Pick A and Pick B, respecting shelves and cross-aisles.
    """
    # If in the same aisle, it's a straight line
    if (pick_a.physical_aisle_id == pick_b.physical_aisle_id and 
            pick_a.physical_aisle_id is not None and 
            pick_a.physical_aisle_id != 0):
        return [(pick_a.x, pick_a.y), (pick_b.x, pick_b.y)]
    
    # Calculate which routing path (top, mid, bottom) is shortest
    x_dist = abs(pick_a.x - pick_b.x)
    
    y_top = 0.0
    
    shelf_len = warehouse.geometry.shelf_length_m
    first_section_end = warehouse.rows_config["first_section_end"]
    cross_width = warehouse.geometry.cross_aisle_width_m
    
    y_mid = (first_section_end * shelf_len) + (cross_width / 2.0)
    
    total_rows = warehouse.rows_config["end"] - warehouse.rows_config["start"] + 1
    y_bottom = (total_rows * shelf_len) + cross_width
    
    dist_top = abs(pick_a.y - y_top) + x_dist + abs(pick_b.y - y_top)
    dist_mid = abs(pick_a.y - y_mid) + x_dist + abs(pick_b.y - y_mid)
    dist_bottom = abs(pick_a.y - y_bottom) + x_dist + abs(pick_b.y - y_bottom)
    
    # Select the transition corridor y coordinate
    min_dist = min(dist_top, dist_mid, dist_bottom)
    if min_dist == dist_top:
        y_trans = y_top
    elif min_dist == dist_mid:
        y_trans = y_mid
    else:
        y_trans = y_bottom
        
    # Return the path vertices:
    # 1. Start at A
    # 2. Walk along A's aisle to the cross-aisle y_trans
    # 3. Walk along cross-aisle from A's x to B's x
    # 4. Walk along B's aisle to B's y
    return [
        (pick_a.x, pick_a.y),
        (pick_a.x, y_trans),
        (pick_b.x, y_trans),
        (pick_b.x, pick_b.y)
    ]

def draw_warehouse_map(warehouse: Warehouse, route: List[Pick] = None) -> go.Figure:
    fig = go.Figure()
    
    # Dimensions
    shelf_len = warehouse.geometry.shelf_length_m
    shelf_depth = warehouse.geometry.shelf_depth_m
    first_section_end = warehouse.rows_config["first_section_end"]
    second_section_start = warehouse.rows_config["second_section_start"]
    total_rows = warehouse.rows_config["end"] - warehouse.rows_config["start"] + 1
    cross_width = warehouse.geometry.cross_aisle_width_m
    
    y_section1_end = first_section_end * shelf_len
    y_section2_start = y_section1_end + cross_width
    y_max = (total_rows * shelf_len) + cross_width
    
    # 1. Draw shelves and unified aisle containers
    for aisle in warehouse.aisles:
        x_c = aisle.x_position_m
        r_limit = 1.25 if aisle.right_side is not None else 0.65
        
        # Draw unified aisle container outline for Section 1 (Rows 1-42)
        fig.add_shape(
            type="rect",
            x0=x_c - 1.25, y0=0.0, x1=x_c + r_limit, y1=y_section1_end,
            fillcolor="rgba(241, 245, 249, 0.4)",
            line=dict(color="rgba(148, 163, 184, 0.6)", width=1.5),
            name=f"Gang {aisle.id} Container (1-42)"
        )
        
        # Draw unified aisle container outline for Section 2 (Rows 43-84)
        fig.add_shape(
            type="rect",
            x0=x_c - 1.25, y0=y_section2_start, x1=x_c + r_limit, y1=y_max,
            fillcolor="rgba(241, 245, 249, 0.4)",
            line=dict(color="rgba(148, 163, 184, 0.6)", width=1.5),
            name=f"Gang {aisle.id} Container (43-84)"
        )

        # Draw Left side shelves (solid slate blocks)
        # Section 1 (Rows 1..42)
        fig.add_shape(
            type="rect",
            x0=x_c - 1.25, y0=0.0, x1=x_c - 0.65, y1=y_section1_end,
            fillcolor="rgba(71, 85, 105, 0.9)",
            line=dict(color="rgb(51, 65, 85)", width=1),
            name=f"Regalseite {aisle.left_side:02d} (1-42)"
        )
        # Section 2 (Rows 43..84)
        fig.add_shape(
            type="rect",
            x0=x_c - 1.25, y0=y_section2_start, x1=x_c - 0.65, y1=y_max,
            fillcolor="rgba(71, 85, 105, 0.9)",
            line=dict(color="rgb(51, 65, 85)", width=1),
            name=f"Regalseite {aisle.left_side:02d} (43-84)"
        )
        
        # Label left side (Side number)
        fig.add_annotation(
            x=x_c - 0.95, y=y_section1_end / 2,
            text=f"S{aisle.left_side:02d}",
            showarrow=False,
            font=dict(size=10, color="white"),
            textangle=-90
        )
        fig.add_annotation(
            x=x_c - 0.95, y=(y_section2_start + y_max) / 2,
            text=f"S{aisle.left_side:02d}",
            showarrow=False,
            font=dict(size=10, color="white"),
            textangle=-90
        )
        
        # Right side shelves if they exist
        if aisle.right_side is not None:
            # Section 1
            fig.add_shape(
                type="rect",
                x0=x_c + 0.65, y0=0.0, x1=x_c + 1.25, y1=y_section1_end,
                fillcolor="rgba(71, 85, 105, 0.9)",
                line=dict(color="rgb(51, 65, 85)", width=1),
                name=f"Regalseite {aisle.right_side:02d} (1-42)"
            )
            # Section 2
            fig.add_shape(
                type="rect",
                x0=x_c + 0.65, y0=y_section2_start, x1=x_c + 1.25, y1=y_max,
                fillcolor="rgba(71, 85, 105, 0.9)",
                line=dict(color="rgb(51, 65, 85)", width=1),
                name=f"Regalseite {aisle.right_side:02d} (43-84)"
            )
            # Label right side (Side number)
            fig.add_annotation(
                x=x_c + 0.95, y=y_section1_end / 2,
                text=f"S{aisle.right_side:02d}",
                showarrow=False,
                font=dict(size=10, color="white"),
                textangle=-90
            )
            fig.add_annotation(
                x=x_c + 0.95, y=(y_section2_start + y_max) / 2,
                text=f"S{aisle.right_side:02d}",
                showarrow=False,
                font=dict(size=10, color="white"),
                textangle=-90
            )
            
        # Draw text labels for Aisles at the top
        fig.add_annotation(
            x=x_c, y=y_max + 2.5,
            text=f"<b>Gang {aisle.id}</b><br>Seite {aisle.left_side:02d}/{f'{aisle.right_side:02d}' if aisle.right_side else '-'}",
            showarrow=False,
            font=dict(size=10, color="rgb(15, 23, 42)"),
            align="center"
        )
        
    # 2. Draw special elements (like rolling cart) dynamically
    for elem in warehouse.special_elements:
        cx = elem["x_position_m"]
        cy = elem["y_position_m"]
        sides_label = "-".join([f"S{s:02d}" for s in elem.get("sides", [])])
        
        fig.add_shape(
            type="rect",
            x0=cx - 0.6, y0=cy - 1.5, x1=cx + 0.6, y1=cy + 0.5,
            fillcolor="rgba(16, 185, 129, 0.4)",
            line=dict(color="rgb(16, 185, 129)", width=2),
            name=elem["name"]
        )
        fig.add_annotation(
            x=cx, y=cy - 0.5,
            text=f"<b>{elem['name']}</b><br>{sides_label}",
            showarrow=False,
            font=dict(size=9, color="rgb(6, 95, 70)"),
            align="center"
        )

    # 3. Draw cross-aisle corridor (Mittel-/Quergang)
    fig.add_shape(
        type="rect",
        x0=-0.5, y0=y_section1_end, x1=23.0, y1=y_section2_start,
        fillcolor="rgba(226, 232, 240, 0.6)",
        line=dict(color="rgba(148, 163, 184, 0.5)", width=1, dash="dash"),
        name="Mittelgang"
    )
    fig.add_annotation(
        x=11.25, y=y_section1_end + (cross_width / 2.0),
        text="Mittel-/Quergang (Breite: 1,43 m)",
        showarrow=False,
        font=dict(size=11, color="rgb(71, 85, 105)")
    )

    # 4. Draw Row boundaries indicators (001, 042, 043, 084)
    # Left edge labels for row numbers
    fig.add_annotation(
        x=-1.5, y=0.5 * shelf_len,
        text="Reihe 001", showarrow=False, font=dict(size=9, color="rgb(100, 116, 139)"), align="right"
    )
    fig.add_annotation(
        x=-1.5, y=y_section1_end - 0.5 * shelf_len,
        text="Reihe 042", showarrow=False, font=dict(size=9, color="rgb(100, 116, 139)"), align="right"
    )
    fig.add_annotation(
        x=-1.5, y=y_section2_start + 0.5 * shelf_len,
        text="Reihe 043", showarrow=False, font=dict(size=9, color="rgb(100, 116, 139)"), align="right"
    )
    fig.add_annotation(
        x=-1.5, y=y_max - 0.5 * shelf_len,
        text="Reihe 084", showarrow=False, font=dict(size=9, color="rgb(100, 116, 139)"), align="right"
    )

    # Walkway indicators
    fig.add_annotation(
        x=11.25, y=-2.0,
        text="Eingang / Endbereich bei Reihe 001",
        showarrow=False, font=dict(size=10, color="rgb(100, 116, 139)")
    )
    fig.add_annotation(
        x=11.25, y=y_max + 1.0,
        text="Ausgang / Endbereich bei Reihe 084",
        showarrow=False, font=dict(size=10, color="rgb(100, 116, 139)")
    )
    
    # 4. Plot path and pick coordinates if a route is provided
    if route:
        # Construct detailed path coordinate points
        path_x = []
        path_y = []
        
        for i in range(len(route) - 1):
            segment = generate_detailed_path_points(route[i], route[i+1], warehouse)
            for pt in segment[:-1]:  # Avoid duplicates at joining points
                path_x.append(pt[0])
                path_y.append(pt[1])
        # Add final point
        if route:
            path_x.append(route[-1].x)
            path_y.append(route[-1].y)
            
        # Draw path lines
        fig.add_trace(go.Scatter(
            x=path_x,
            y=path_y,
            mode="lines",
            line=dict(color="rgb(59, 130, 246)", width=3, dash="solid"),
            name="Laufweg",
            hoverinfo="skip"
        ))
        
        # Add direction arrows (mid-points of segment steps)
        # We can place markers along the path
        arrow_x = []
        arrow_y = []
        for i in range(0, len(path_x) - 1, max(1, len(path_x) // 15)):
            arrow_x.append((path_x[i] + path_x[i+1]) / 2)
            arrow_y.append((path_y[i] + path_y[i+1]) / 2)
            
        fig.add_trace(go.Scatter(
            x=arrow_x,
            y=arrow_y,
            mode="markers",
            marker=dict(symbol="arrow-right", size=8, color="rgb(29, 78, 216)"),
            name="Richtung",
            showlegend=False,
            hoverinfo="skip"
        ))

        # Draw Picks
        pick_x = [p.x for p in route]
        pick_y = [p.y for p in route]
        pick_labels = [
            f"<b>Pick {idx+1}: {p.raw_code}</b><br>"
            f"Seite: {p.side_str}<br>"
            f"Reihe: {p.row_str}<br>"
            f"Box: {p.box_str}<br>"
            f"Physischer Gang: {p.physical_aisle_id}"
            for idx, p in enumerate(route)
        ]
        
        # Scatter for all picks
        fig.add_trace(go.Scatter(
            x=pick_x,
            y=pick_y,
            mode="markers+text",
            marker=dict(
                size=12,
                color="rgb(239, 68, 68)",
                line=dict(color="white", width=2)
            ),
            text=[str(i+1) for i in range(len(route))],
            textposition="middle center",
            textfont=dict(color="white", size=9),
            hovertext=pick_labels,
            hoverinfo="text",
            name="Pick-Positionen"
        ))
        
        # Highlight start point in Green
        fig.add_trace(go.Scatter(
            x=[route[0].x],
            y=[route[0].y],
            mode="markers",
            marker=dict(
                size=16,
                color="rgb(16, 185, 129)",
                line=dict(color="white", width=3)
            ),
            hovertext=(
                f"<b>Startpunkt: {route[0].raw_code}</b><br>"
                f"Seite: {route[0].side_str}<br>"
                f"Reihe: {route[0].row_str}<br>"
                f"Box: {route[0].box_str}<br>"
                f"Physischer Gang: {route[0].physical_aisle_id}"
            ),
            hoverinfo="text",
            name="Startpunkt"
        ))

    # Layout styling
    fig.update_layout(
        title="Lager-Layout & Pick-Route",
        xaxis=dict(
            title="Breite (m)",
            range=[-1.0, 24.0],
            gridcolor="rgba(226, 232, 240, 0.5)",
            zeroline=False
        ),
        yaxis=dict(
            title="Länge (m)",
            range=[-4.0, y_max + 4.0],
            gridcolor="rgba(226, 232, 240, 0.5)",
            zeroline=False
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        width=800,
        height=750,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=40, t=80, b=40)
    )
    
    return fig
