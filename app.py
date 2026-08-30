import streamlit as st
import os
import pandas as pd
from datetime import datetime
from modules.warehouse import Warehouse
from modules.picks import Pick, PickOrder, load_all_batches, save_batch, delete_batch, generate_next_batch_id
from modules.routing import calculate_route_distance, calculate_route_metrics, get_original_route, get_simple_sorted_route
from modules.optimizer_benchmark import (
    benchmark_batch,
    get_comparable_history_runs,
    get_history_objective_summary,
    is_valid_objective_value,
    load_benchmark_history,
    summarize_benchmark_results,
)
from visualization.warehouse_map import draw_warehouse_map

# Page configuration
st.set_page_config(
    page_title="Pick Path Optimizer",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium design
st.markdown("""
<style>
    /* Premium style additions */
    .stApp {
        background-color: #f8fafc;
    }
    .main-header {
        font-family: 'Outfit', 'Inter', sans-serif;
        color: #1e293b;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-family: 'Inter', sans-serif;
        color: #64748b;
        font-weight: 400;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: white;
        padding: 1.25rem;
        border-radius: 0.75rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    .metric-label {
        font-size: 0.875rem;
        color: #64748b;
        font-weight: 500;
    }
    .metric-value {
        font-size: 1.5rem;
        color: #0f172a;
        font-weight: 700;
        margin-top: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "data", "warehouse.json")
BATCHES_PATH = os.path.join(BASE_DIR, "data", "pick_batches.json")
BENCHMARK_HISTORY_PATH = os.path.join(BASE_DIR, "data", "benchmark_history.json")

# Initialize warehouse (cached)
@st.cache_resource
def load_warehouse():
    return Warehouse(CONFIG_PATH)

try:
    warehouse = load_warehouse()
except Exception as e:
    st.error(f"Fehler beim Laden der Lagerkonfiguration: {e}")
    st.stop()

# Sidebar Navigation
st.sidebar.image("https://img.icons8.com/color/96/delivery-box.png", width=80)
st.sidebar.markdown("<h2 style='margin-top:0;'>Pick Path Optimizer</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

navigation = st.sidebar.radio(
    "Navigation",
    ["1. Übersicht", "2. Lagerdaten", "3. Pick-Batches", "4. Lagerkarte", "5. Routenvergleich", "6. Benchmark", "7. Einstellungen"]
)

# ----------------------------------------------------
# Page 1: Übersicht
# ----------------------------------------------------
if navigation == "1. Übersicht":
    st.markdown("<h1 class='main-header'>Pick Path Optimizer</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Mathematische Analyse und Laufwegoptimierung für die Lagerlogistik</p>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-label'>Physische Gänge</div>
            <div class='metric-value'>9</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-label'>Stellplatzseiten</div>
            <div class='metric-value'>18 + Wagen (01-03)</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-label'>Reihen pro Gang</div>
            <div class='metric-value'>84 (001 - 084)</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class='metric-card'>
            <div class='metric-label'>Länge Hauptgang</div>
            <div class='metric-value'>ca. 110,63 m</div>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("### Über das Projekt")
    st.write(
        "Der **Pick Path Optimizer** dient der Analyse und Optimierung von Laufwegen im Kommissionierprozess. "
        "Durch die mathematische Abbildung des realen Lagers (inklusive Quergängen, Regaltiefen und Gassen) "
        "kann das System Laufwege berechnen, simulieren und Einsparpotenziale aufzeigen."
    )
    
    st.markdown("### Funktionsweise in Schritt 1")
    st.markdown(
        "1. **Strukturierte Erfassung:** Das Lager wird über eine zentrale `warehouse.json` konfiguriert (Shelf-Maße, Quergangbreiten, x-Koordinaten).\n"
        "2. **Picknummern-Parsing:** Eingaben der Form `XX.YYY.ZZ` werden in Gang/Seite, Reihe und Box zerlegt.\n"
        "3. **Wegberechnung:** Berechnung der tatsächlichen Fußwege unter Berücksichtigung der Gassenstruktur sowie der Übergänge (Eingang Reihe 001, Mittel-/Quergang und Ausgang Reihe 084).\n"
        "4. **Visualisierung:** Interaktive 2D-Lagerkarte zur Darstellung der berechneten Routen."
    )

# ----------------------------------------------------
# Page 2: Lagerdaten
# ----------------------------------------------------
elif navigation == "2. Lagerdaten":
    st.markdown("<h1 class='main-header'>Lagerkonfiguration</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Ausgelesene Parameter aus der zentralen JSON-Konfigurationsdatei</p>", unsafe_allow_html=True)
    
    st.subheader("Geometrische Maße")
    geo = warehouse.geometry
    geo_data = {
        "Parameter": [
            "Regallänge (m)", "Regalhöhe (m)", "Regaltiefe (m)", 
            "Hauptwegbreite im Regalbereich (m)", "Mittel-/Quergang Breite (m)"
        ],
        "Wert": [
            geo.shelf_length_m, geo.shelf_height_m, geo.shelf_depth_m,
            geo.main_aisle_width_m, geo.cross_aisle_width_m
        ]
    }
    st.table(pd.DataFrame(geo_data))
    
    st.subheader("Regalgänge und Stellplatzseiten")
    aisle_list = []
    for aisle in warehouse.aisles:
        aisle_list.append({
            "Aisle ID": aisle.id,
            "Name": aisle.name,
            "Linke Seite": f"{aisle.left_side:02d}",
            "Rechte Seite": f"{aisle.right_side:02d}" if aisle.right_side is not None else "Keine zweite Seite (20)",
            "Reihenbereich": f"{aisle.row_start:03d} - {aisle.row_end:03d}",
            "X-Koordinate (m)": aisle.x_position_m
        })
    st.dataframe(pd.DataFrame(aisle_list), use_container_width=True)
    
    st.subheader("Spezielle Stellplätze")
    for elem in warehouse.special_elements:
        st.info(f"**{elem['name']}:** Seiten {elem['sides']} auf x={elem['x_position_m']}m, y={elem['y_position_m']}m (neben Gang 4)")



# ----------------------------------------------------
# Page 3: Pick-Batches
# ----------------------------------------------------
elif navigation == "3. Pick-Batches":
    st.markdown("<h1 class='main-header'>Pick-Batches</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Verwalten Sie Ihre Kommissionieraufträge: Neue Batches eingeben, validieren, speichern und historische Batches einsehen.</p>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🆕 Neue Batch erfassen", "📜 Batch-Historie"])
    
    with tab1:
        st.subheader("Pick-Codes eingeben")
        st.write("Geben Sie eine Liste von Pick-Codes untereinander (ein Code pro Zeile) ein. Format: `XX.YYY.ZZ` (z.B. `19.015.20`).")
        
        # Helper to prefill test batch
        prefill = st.button("Mit realer Test-Batch (33 Picks) vorausfüllen", key="prefill_button")
        
        test_batch_raw = (
            "05.056.50\n06.008.30\n07.002.30\n07.004.30\n08.041.30\n"
            "10.051.20\n10.046.40\n10.039.30\n10.029.30\n10.027.30\n"
            "10.019.30\n10.001.40\n11.066.40\n12.074.40\n12.033.10\n"
            "13.009.10\n13.038.30\n13.073.50\n15.031.20\n15.034.30\n"
            "15.042.30\n15.045.30\n15.075.40\n16.031.30\n16.027.20\n"
            "17.027.30\n17.035.30\n17.084.40\n18.045.10\n19.015.20\n"
            "19.023.50\n20.028.10\n20.020.30"
        )
        
        default_val = test_batch_raw if prefill else ""
        
        raw_input = st.text_area(
            "Pick-Codes",
            value=default_val,
            height=250,
            placeholder="z.B.\n05.056.50\n06.008.30\n...",
            key="input_textarea"
        )
        
        if st.button("Batch validieren und speichern", key="save_button"):
            if not raw_input.strip():
                st.warning("Bitte geben Sie zuerst Pick-Codes ein.")
            else:
                # Split lines and strip whitespaces
                lines = [line.strip() for line in raw_input.split("\n") if line.strip()]
                
                # Validate picks
                errors = []
                valid_picks = []
                for idx, code in enumerate(lines):
                    try:
                        p = Pick(code, warehouse)
                        valid_picks.append(p)
                    except ValueError as e:
                        errors.append((idx + 1, code, str(e)))
                
                if errors:
                    st.error(f"Validierung fehlgeschlagen! {len(errors)} Fehler gefunden:")
                    for line_num, code, err in errors:
                        st.error(f"Zeile {line_num}: '{code}' -> {err}")
                else:
                    # Load existing batches to generate next ID
                    all_batches = load_all_batches(BATCHES_PATH, warehouse)
                    new_id = generate_next_batch_id(list(all_batches.keys()))
                    
                    now_str = datetime.now().isoformat()
                    
                    new_order = PickOrder(
                        order_id=new_id,
                        timestamp_str=now_str,
                        raw_picks_list=lines,
                        warehouse=warehouse,
                        source="manual"
                    )
                    
                    try:
                        save_batch(BATCHES_PATH, new_order)
                        st.success(f"Batch {new_id} erfolgreich validiert und unter '{new_id}' gespeichert!")
                        
                        # Summary Metrics
                        st.markdown("### 📊 Batch-Zusammenfassung (Datenqualität)")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Picks (Total)", len(valid_picks))
                            st.metric("Physische Gänge", len(set(p.physical_aisle_id for p in valid_picks if p.physical_aisle_id is not None)))
                        with col2:
                            st.metric("Erster Pick (first_pick)", valid_picks[0].raw_code if valid_picks else "-")
                            st.metric("Letzter Pick", valid_picks[-1].raw_code if valid_picks else "-")
                        with col3:
                            st.metric("Verschiedene Stellplatzseiten", len(set(p.side for p in valid_picks)))
                            st.metric("Fehler", "0")
                            
                    except Exception as e:
                        st.error(f"Fehler beim Speichern der Batch: {e}")
                        
    with tab2:
        st.subheader("Bestehende Pick-Batches")
        all_batches = load_all_batches(BATCHES_PATH, warehouse)
        
        if not all_batches:
            st.info("Keine gespeicherten Batches in der Datenbank gefunden.")
        else:
            # Build DataFrame of existing batches
            records = []
            for b_id, b in all_batches.items():
                formatted_date = b.timestamp.strftime("%Y-%m-%d %H:%M:%S") if hasattr(b, "timestamp") else b.created_at
                records.append({
                    "Batch-ID": b.order_id,
                    "Datum": formatted_date,
                    "Anzahl Picks": b.pick_count,
                    "Erster Pick": b.first_pick.raw_code if b.first_pick else "-",
                    "Letzter Pick": b.last_input_pick.raw_code if b.last_input_pick else "-",
                    "Quelle": "Manuell" if b.source == "manual" else "Historischer Testauftrag"
                })
            
            df_records = pd.DataFrame(records)
            st.dataframe(df_records, use_container_width=True, hide_index=True)
            
            # Select batch for detail view / actions
            st.markdown("---")
            selected_id = st.selectbox(
                "Wählen Sie eine Batch für Details oder Aktionen aus:",
                options=list(all_batches.keys()),
                key="history_selectbox"
            )
            
            if selected_id:
                selected_batch = all_batches[selected_id]
                
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"**Batch-ID:** `{selected_batch.order_id}`")
                    st.write(f"**Erstellungsdatum:** `{selected_batch.timestamp.strftime('%Y-%m-%d %H:%M:%S')}`")
                    st.write(f"**Anzahl Picks:** `{selected_batch.pick_count}`")
                with c2:
                    st.write(f"**Quelle:** {selected_batch.source}")
                    st.write(f"**Erster Pick:** `{selected_batch.first_pick.raw_code if selected_batch.first_pick else '-'}`")
                    st.write(f"**Letzter Pick:** `{selected_batch.last_input_pick.raw_code if selected_batch.last_input_pick else '-'}`")
                
                # Detailed list of picks
                df_picks_detail = []
                for idx, p in enumerate(selected_batch.picks):
                    df_picks_detail.append({
                        "Pos": idx + 1,
                        "Code": p.raw_code,
                        "Seite": p.side_str,
                        "Reihe": p.row_str,
                        "Box": p.box_str,
                        "Physischer Gang": p.physical_aisle_id,
                        "Koord X": round(p.x, 3),
                        "Koord Y": round(p.y, 3)
                    })
                st.dataframe(pd.DataFrame(df_picks_detail), use_container_width=True, hide_index=True)
                
                # Redirect to map button
                if st.button("Auf Karte anzeigen 🗺️", key=f"show_map_{selected_id}"):
                    st.session_state["selected_batch_id"] = selected_id
                    st.success("Batch geladen! Wechseln Sie zur '4. Lagerkarte', um sie anzuzeigen.")
                
                # Delete batch section
                st.markdown("#### Gefahrenbereich")
                confirm_del = st.checkbox(
                    f"Ich bestätige, dass ich die Batch '{selected_id}' unwiderruflich löschen möchte.",
                    key=f"confirm_{selected_id}"
                )
                if st.button("Batch unwiderruflich löschen 🗑️", key=f"del_{selected_id}", disabled=not confirm_del):
                    if delete_batch(BATCHES_PATH, selected_id):
                        st.success(f"Batch {selected_id} wurde erfolgreich gelöscht.")
                        st.rerun()
                    else:
                        st.error(f"Fehler beim Löschen der Batch.")

# ----------------------------------------------------
# Page 4: Lagerkarte
# ----------------------------------------------------
elif navigation == "4. Lagerkarte":
    st.markdown("<h1 class='main-header'>Interaktive Lagerkarte</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Geben Sie Pick-Codes ein oder laden Sie eine gespeicherte Batch, um die Route anzuzeigen</p>", unsafe_allow_html=True)
    
    # Load all batches for dropdown selection
    all_batches = load_all_batches(BATCHES_PATH, warehouse)
    
    # Check if a batch was passed via session state
    selected_batch_id_default = st.session_state.get("selected_batch_id", "-- Manuelle Eingabe --")
    if selected_batch_id_default != "-- Manuelle Eingabe --" and selected_batch_id_default not in all_batches:
        selected_batch_id_default = "-- Manuelle Eingabe --"
        
    dropdown_options = ["-- Manuelle Eingabe --"] + list(all_batches.keys())
    default_idx = dropdown_options.index(selected_batch_id_default)
    
    loaded_batch_id = st.selectbox(
        "Gespeicherte Batch laden",
        options=dropdown_options,
        index=default_idx,
        key="map_load_selectbox"
    )
    
    parsed_picks = []
    
    if loaded_batch_id != "-- Manuelle Eingabe --":
        st.info(f"Geladene Batch: **{loaded_batch_id}** ({all_batches[loaded_batch_id].pick_count} Picks, Quelle: {all_batches[loaded_batch_id].source})")
        parsed_picks = all_batches[loaded_batch_id].picks
        # Clear session state default after loading
        if "selected_batch_id" in st.session_state:
            del st.session_state["selected_batch_id"]
    else:
        # Input field for custom picks
        default_picks = "04.002.30; 04.015.30; 04.059.30; 05.014.20; 05.076.20; 09.041.30; 17.060.40; 20.034.10"
        pick_input = st.text_input(
            "Kommissionierliste eingeben (Semikolon-separiert)",
            value=default_picks,
            help="Format: XX.YYY.ZZ (z.B. 19.015.20)",
            key="map_pick_input"
        )
        
        # Parse picks
        raw_codes = [code.strip() for code in pick_input.split(";") if code.strip()]
        invalid_picks = []
        for code in raw_codes:
            try:
                parsed_picks.append(Pick(code, warehouse))
            except ValueError as e:
                invalid_picks.append((code, str(e)))
                
        if invalid_picks:
            for code, err in invalid_picks:
                st.error(f"Ungültiger Pick-Code '{code}': {err}")
                
    if parsed_picks:
        # Routing Options
        route_type = st.radio(
            "Routenberechnungsmethode",
            ["Originale Reihenfolge (Unoptimiert)", "Einfache Gassen-Sortierung (S-Shape - PROVISORISCHER TEST – NICHT OPTIMIERT)"],
            horizontal=True,
            key="routing_radio"
        )
        
        # Calculate routes
        if route_type == "Originale Reihenfolge (Unoptimiert)":
            route = get_original_route(parsed_picks)
        else:
            route = get_simple_sorted_route(parsed_picks, warehouse)
            
        # Draw Map
        fig = draw_warehouse_map(warehouse, route)
        
        # Calculate statistics and segments
        metrics = calculate_route_metrics(route, warehouse)
        orig_metrics = calculate_route_metrics(parsed_picks, warehouse)
        
        col1, col2 = st.columns([3, 7])
        
        with col1:
            st.markdown("### Routen-Statistik")
            
            # Displays
            st.metric("Laufweg der Route", f"{metrics.total_distance_m:.2f} m")
            
            if route_type == "Einfache Gassen-Sortierung (S-Shape - PROVISORISCHER TEST – NICHT OPTIMIERT)":
                savings_dist = orig_metrics.total_distance_m - metrics.total_distance_m
                savings_pct = (savings_dist / orig_metrics.total_distance_m * 100) if orig_metrics.total_distance_m > 0 else 0
                st.metric("Vergleich unoptimierter Weg", f"{orig_metrics.total_distance_m:.2f} m")
                if savings_dist > 0:
                    st.success(f"Ersparnis: {savings_dist:.2f} m ({savings_pct:.1f}%)")
                elif savings_dist < 0:
                    st.warning(f"Sortierte Route ist {-savings_dist:.2f} m länger als die unoptimierte.")
            
            st.markdown("**Weitere Details:**")
            st.write(f"- **Picks:** {metrics.pick_count}")
            st.write(f"- **Gänge besucht:** {metrics.physical_aisles_visited}")
            st.write(f"- **Ø Distanz pro Pick:** {metrics.average_segment_m:.2f} m")
            st.write(f"- **Längstes Segment:** {metrics.longest_segment_m:.2f} m")
            st.write(f"- **Kürzestes Segment:** {metrics.shortest_segment_m:.2f} m")
                
            st.markdown("---")
            st.markdown("### Pick-Reihenfolge")
            df_order = []
            for i, p in enumerate(route):
                df_order.append({
                    "Pos": i + 1,
                    "Code": p.raw_code
                })
            st.dataframe(pd.DataFrame(df_order), use_container_width=True, hide_index=True)
            
        with col2:
            st.plotly_chart(fig, use_container_width=True)
            
        # Draw validation table and segment table under the map/columns
        st.markdown("---")
        
        # Draw Route Segments Table
        st.markdown("### Routen-Tabelle (Segment-Details)")
        df_segments = []
        for idx, seg in enumerate(metrics.segments):
            df_segments.append({
                "#": idx + 1,
                "Von": seg.start_pick.raw_code,
                "Nach": seg.end_pick.raw_code,
                "Weg": seg.chosen_path_type,
                "Distanz": f"{seg.distance_m:.2f} m"
            })
        st.dataframe(pd.DataFrame(df_segments), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("### Validierungs-Informationen (Koordinatenkontrolle)")
        df_picks = []
        for p in route:
            df_picks.append({
                "Pick": p.raw_code,
                "Seite": p.side_str,
                "Reihe": p.row_str,
                "Box": p.box_str,
                "Physischer Gang": p.physical_aisle_id,
                "X": round(p.x, 3),
                "Y": round(p.y, 3)
            })
        st.dataframe(pd.DataFrame(df_picks), use_container_width=True, hide_index=True)

# ----------------------------------------------------
# Page 5: Routenvergleich
# ----------------------------------------------------
elif navigation == "5. Routenvergleich":
    st.markdown("<h1 class='main-header'>Heuristischer Routenvergleich</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Vergleichen Sie verschiedene Optimierungsheuristiken gegen Ihre geladenen Kommissionieraufträge</p>", unsafe_allow_html=True)
    
    all_batches = load_all_batches(BATCHES_PATH, warehouse)
    
    if not all_batches:
        st.warning("Keine Kommissionieraufträge in der Datenbank gefunden. Bitte erfassen Sie zuerst eine Batch im Reiter '3. Pick-Batches'.")
    else:
        # Dropdown to select batch
        selected_batch_id = st.selectbox(
            "Wählen Sie einen Auftrag für den Vergleich aus:",
            options=list(all_batches.keys()),
            key="benchmark_batch_selectbox"
        )
        
        batch_order = all_batches[selected_batch_id]
        
        # Trigger benchmark
        results = benchmark_batch(
            batch_order.picks, warehouse, selected_batch_id, persist=False
        )
        
        # Display comparison table
        st.markdown("### 📊 Benchmark-Ergebnisse")
        
        winner_summary = summarize_benchmark_results(results)
        baseline_dist = winner_summary["baseline_distance_with_exit_m"]

        df_comp = []
        for r in results:
            difference_m = baseline_dist - r["distance_with_exit_m"]
            difference_pct = (difference_m / baseline_dist * 100) if baseline_dist > 0 else 0.0
            if r["method_name"] == "Baseline":
                difference_str = "Baseline"
            elif difference_m > 0:
                difference_str = f"{difference_m:.2f} m kürzer ({difference_pct:.1f}%)"
            elif difference_m < 0:
                difference_str = f"{-difference_m:.2f} m länger ({-difference_pct:.1f}%)"
            else:
                difference_str = "Gleich lang wie Baseline"
            
            df_comp.append({
                "Methode": r["method_name"],
                "Pick-Distanz (m)": f"{r['total_distance_m']:.2f} m",
                "Weg zum Ausgang (m)": f"{r['end_distance_to_20_001_m']:.2f} m",
                "Gesamtdistanz inklusive Ausgang (m)": f"{r['distance_with_exit_m']:.2f} m",
                "Differenz zur Baseline": difference_str,
                "Besuchte Gänge": r["physical_aisles_visited"],
                "Backtracking (m)": f"{r['estimated_backtracking_distance_m']:.2f} m",
                "Via Mitte": r["via_middle_count"],
                "Max. Längslauf (m)": f"{r['max_single_aisle_traversal_m']:.2f} m",
                "Wiederholte Gänge": r["repeated_aisle_visit_count"],
                "Gültig?": "✅ Ja" if r["is_valid"] else "❌ Nein"
            })
                
        st.dataframe(pd.DataFrame(df_comp), use_container_width=True, hide_index=True)

        best_method = winner_summary["best_heuristic_method"]
        best_dist = winner_summary["best_heuristic_distance_with_exit_m"]
        if winner_summary["heuristic_improves_baseline"]:
            saving_m = baseline_dist - best_dist
            saving_pct = (saving_m / baseline_dist * 100) if baseline_dist > 0 else 0.0
            st.success(
                f"🏆 **Beste Methode einschließlich Baseline:** {winner_summary['best_overall_method']} – "
                f"Distanz inklusive Ausgang: {best_dist:.2f} m "
                f"({saving_m:.2f} m bzw. {saving_pct:.1f}% kürzer als die Baseline)."
            )
        else:
            st.warning("Keine getestete Heuristik verbessert die Baseline.")
            st.info(
                f"Beste getestete Heuristik: {best_method} mit {best_dist:.2f} m Distanz "
                f"inklusive Ausgang. Beste Methode einschließlich Baseline: "
                f"{winner_summary['best_overall_method']}."
            )
            
        # Select method to visualize
        st.markdown("---")
        st.markdown("### 🗺️ Routen-Visualisierung")
        
        route_options = [r["method_name"] for r in results if r["is_valid"]]
        selected_method = st.selectbox(
            "Wählen Sie eine Heuristik zur Kartenanzeige:",
            options=route_options,
            key="benchmark_show_selectbox"
        )
        
        # Find chosen run
        chosen_run = next(r for r in results if r["method_name"] == selected_method)
        
        # Re-resolve picks from codes for visualizer
        route_picks = [Pick(code, warehouse) for code in chosen_run["route_codes"]]
        
        # Calculate full metrics for visualization
        route_metrics = calculate_route_metrics(route_picks, warehouse)
        
        # Draw Map
        fig = draw_warehouse_map(warehouse, route_picks)
        
        col1, col2 = st.columns([3, 7])
        with col1:
            st.markdown(f"#### Details: {selected_method}")
            st.metric("Pick-Distanz", f"{chosen_run['total_distance_m']:.2f} m")
            st.metric("Weg zum Ausgang", f"{chosen_run['end_distance_to_20_001_m']:.2f} m")
            st.metric("Gesamtdistanz inklusive Ausgang", f"{chosen_run['distance_with_exit_m']:.2f} m")
            
            st.markdown("**Metriken:**")
            st.write(f"- **Picks:** {chosen_run['pick_count']}")
            st.write(f"- **Besuchte Gänge:** {chosen_run['physical_aisles_visited']}")
            st.write(f"- **Ø Distanz pro Pick:** {chosen_run['average_segment_m']:.2f} m")
            st.write(f"- **Längstes Segment:** {chosen_run['longest_segment_m']:.2f} m")
            st.write(f"- **Kürzestes Segment:** {chosen_run['shortest_segment_m']:.2f} m")
            st.write(f"- **Gangwechsel (Via Mitte):** {chosen_run['via_middle_count']}")
            st.write(f"- **Gangwechsel (Via 001/084):** {chosen_run['via_001_count'] + chosen_run['via_084_count']}")
            st.write(f"- **Richtungswechsel:** {chosen_run['direction_changes']}")
            st.write(f"- **Backtracking-Länge:** {chosen_run['estimated_backtracking_distance_m']:.2f} m")
            
            st.markdown("---")
            st.markdown("#### Pick-Reihenfolge")
            
            # Determine aisle directions dynamically
            unique_aisle_ids = sorted(list(set(p.physical_aisle_id for p in route_picks if p.physical_aisle_id is not None)))
            aisle_directions = {}
            for a_id in unique_aisle_ids:
                y_coords = [p.y for p in route_picks if p.physical_aisle_id == a_id]
                if len(y_coords) <= 1:
                    aisle_directions[a_id] = "N/A"
                else:
                    if y_coords[-1] >= y_coords[0]:
                        aisle_directions[a_id] = "UP (001 ➔ 084)"
                    else:
                        aisle_directions[a_id] = "DOWN (084 ➔ 001)"
            if 0 in aisle_directions:
                aisle_directions[0] = "Wagen"
                
            df_seq = []
            for idx, p in enumerate(route_picks):
                a_id = p.physical_aisle_id if p.physical_aisle_id is not None else 0
                df_seq.append({
                    "Pos": idx + 1,
                    "Pick": p.raw_code,
                    "Physischer Gang": f"Gang {a_id}" if a_id > 0 else "Wagen",
                    "Richtung": aisle_directions.get(a_id, "N/A")
                })
            st.dataframe(pd.DataFrame(df_seq), use_container_width=True, hide_index=True)
            
        with col2:
            st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------
# Page 6: Benchmark
# ----------------------------------------------------
elif navigation == "6. Benchmark":
    st.markdown("<h1 class='main-header'>Real-Data Benchmarking & Simulation</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Führen Sie vergleichende Benchmarks für Ihre Kommissionieraufträge aus und analysieren Sie aggregierte Statistiken.</p>", unsafe_allow_html=True)
    
    # Load batches
    all_batches = load_all_batches(BATCHES_PATH, warehouse)
    
    # Create tabs
    tab_run, tab_history, tab_sim = st.tabs(["🚀 Benchmark ausführen", "📜 Benchmark-Historie & Profil", "🎲 Simulation / Testdaten"])
    
    with tab_run:
        if not all_batches:
            st.warning("Keine Kommissionieraufträge in der Datenbank gefunden. Bitte erfassen Sie zuerst eine Batch im Reiter '3. Pick-Batches'.")
        else:
            selected_batch_id = st.selectbox(
                "Wählen Sie einen Auftrag für den Benchmark aus:",
                options=list(all_batches.keys()),
                key="run_benchmark_batch_selectbox"
            )
            
            selected_batch = all_batches[selected_batch_id]
            
            # Show batch profile / quality metrics
            st.markdown("### 🔍 Auftragsprofil & Datenqualität")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Anzahl Picks", len(selected_batch.picks))
            with c2:
                st.metric("Besuchte physische Gänge", len(set(p.physical_aisle_id for p in selected_batch.picks if p.physical_aisle_id is not None)))
            with c3:
                st.metric("Verschiedene Stellplatzseiten", len(set(p.side for p in selected_batch.picks)))
            with c4:
                min_r = min(p.row for p in selected_batch.picks) if selected_batch.picks else 0
                max_r = max(p.row for p in selected_batch.picks) if selected_batch.picks else 0
                st.metric("Reihenbereich", f"{min_r:03d} - {max_r:03d}")
                
            # Density bar chart
            st.markdown("**Pick-Dichte pro physischem Gang:**")
            density_data = {}
            for a_id in range(1, 10):
                density_data[f"Gang {a_id}"] = sum(1 for p in selected_batch.picks if p.physical_aisle_id == a_id)
            st.bar_chart(pd.DataFrame(list(density_data.items()), columns=["Physischer Gang", "Picks"]).set_index("Physischer Gang"))
            
            if st.button("Benchmark ausführen", key="run_benchmark_button"):
                with st.spinner("Berechne Routen für alle 6 Optimierungsansätze..."):
                    results = benchmark_batch(selected_batch.picks, warehouse, selected_batch_id, selected_batch.source)
                    
                    winner_summary = summarize_benchmark_results(results)
                    baseline_dist = winner_summary["baseline_distance_with_exit_m"]
                    best_dist = winner_summary["best_heuristic_distance_with_exit_m"]
                    best_method = winner_summary["best_heuristic_method"]
                    if winner_summary["heuristic_improves_baseline"]:
                        saving_m = baseline_dist - best_dist
                        saving_pct = (saving_m / baseline_dist * 100) if baseline_dist > 0 else 0.0
                        st.success(
                            f"🏆 **Benchmark abgeschlossen! Beste Methode einschließlich Baseline:** "
                            f"**{winner_summary['best_overall_method']}** mit **{best_dist:.2f} m "
                            f"Distanz inklusive Ausgang** ({saving_m:.2f} m bzw. "
                            f"{saving_pct:.1f}% kürzer als die Baseline)."
                        )
                    else:
                        st.warning("Keine getestete Heuristik verbessert die Baseline.")
                        st.info(
                            f"Beste getestete Heuristik: {best_method} mit {best_dist:.2f} m Distanz "
                            f"inklusive Ausgang. Beste Methode einschließlich Baseline: "
                            f"{winner_summary['best_overall_method']}."
                        )
                    
                    # Display results sorted by distance ascending
                    sorted_results = sorted(results, key=lambda r: r["distance_with_exit_m"])
                    
                    df_comp = []
                    for r in sorted_results:
                        difference_m = baseline_dist - r["distance_with_exit_m"]
                        difference_pct = (difference_m / baseline_dist * 100) if baseline_dist > 0 else 0.0
                        if r["method_name"] == "Baseline":
                            difference_str = "Baseline"
                        elif difference_m > 0:
                            difference_str = f"{difference_m:.2f} m kürzer ({difference_pct:.1f}%)"
                        elif difference_m < 0:
                            difference_str = f"{-difference_m:.2f} m länger ({-difference_pct:.1f}%)"
                        else:
                            difference_str = "Gleich lang wie Baseline"
                        
                        df_comp.append({
                            "Methode": r["method_name"],
                            "Pick-Distanz (m)": f"{r['total_distance_m']:.2f} m",
                            "Weg zum Ausgang (m)": f"{r['end_distance_to_20_001_m']:.2f} m",
                            "Gesamtdistanz inklusive Ausgang (m)": f"{r['distance_with_exit_m']:.2f} m",
                            "Differenz zur Baseline": difference_str,
                            "Besuchte Gänge": r["physical_aisles_visited"],
                            "Backtracking (m)": f"{r['estimated_backtracking_distance_m']:.2f} m",
                            "Via Mitte": r["via_middle_count"],
                            "Max. Längslauf (m)": f"{r['max_single_aisle_traversal_m']:.2f} m",
                            "Wiederholte Gänge": r["repeated_aisle_visit_count"],
                            "Gültig?": "✅ Ja" if r["is_valid"] else "❌ Nein"
                        })
                    st.dataframe(pd.DataFrame(df_comp), use_container_width=True, hide_index=True)
                    
    with tab_history:
        history = load_benchmark_history(BENCHMARK_HISTORY_PATH)
        
        if not history:
            st.info("Noch keine gespeicherten Benchmarks vorhanden. Bitte führen Sie zuerst einen Benchmark aus.")
        else:
            runs = list(history.values())
            
            # Filtering
            filter_source = st.radio("Historie filtern nach Quelle:", ["Echte historische Daten", "Synthetische Simulationsdaten", "Alle anzeigen"], horizontal=True, key="history_filter_radio")
            
            if filter_source == "Echte historische Daten":
                filtered_runs = [r for r in runs if r.get("source", "historical") == "historical"]
            elif filter_source == "Synthetische Simulationsdaten":
                filtered_runs = [r for r in runs if r.get("source", "historical") == "simulation"]
            else:
                filtered_runs = runs
                
            if not filtered_runs:
                st.info("Keine Einträge für diese Filtereinstellung vorhanden.")
            else:
                # History table
                records = []
                for r in filtered_runs:
                    objective_summary = get_history_objective_summary(r)
                    if objective_summary:
                        best_method = objective_summary["best_heuristic_method"]
                        best_overall_method = objective_summary["best_overall_method"]
                        best_val = objective_summary["best_heuristic_distance_with_exit_m"]
                        baseline_val = objective_summary["baseline_distance_with_exit_m"]
                        difference_m = baseline_val - best_val
                        difference_pct = (difference_m / baseline_val * 100) if baseline_val > 0 else 0.0
                        baseline_display = f"{baseline_val:.2f} m"
                        best_display = f"{best_val:.2f} m"
                        if difference_m > 0:
                            difference_display = f"{difference_m:.2f} m kürzer ({difference_pct:.1f}%)"
                        elif difference_m < 0:
                            difference_display = f"{-difference_m:.2f} m länger ({-difference_pct:.1f}%)"
                        else:
                            difference_display = "Gleich lang"
                        if objective_summary["heuristic_improves_baseline"]:
                            result_display = "Beste Heuristik verbessert die Baseline."
                        else:
                            result_display = "Keine getestete Heuristik verbessert die Baseline."
                    else:
                        best_method = "Legacy – Benchmark neu ausführen"
                        best_overall_method = "Legacy – nicht vergleichbar"
                        baseline_display = "Legacy/ungültig"
                        best_display = "Legacy/ungültig"
                        difference_display = "–"
                        result_display = "Nicht für Gewinner oder Aggregate verwendet"
                    
                    records.append({
                        "Batch-ID": r.get("batch_id", "Unbekannt"),
                        "Picks": r.get("pick_count", "–"),
                        "Quelle": "Manuell / Historisch" if r.get("source", "historical") == "historical" else "Simulation / Synthetisch",
                        "Baseline – Distanz inklusive Ausgang": baseline_display,
                        "Beste Heuristik – Distanz inklusive Ausgang": best_display,
                        "Differenz zur Baseline": difference_display,
                        "Beste Heuristik": best_method,
                        "Beste Methode einschließlich Baseline": best_overall_method,
                        "Ergebnis": result_display,
                        "Datum": r.get("timestamp", "Unbekannt")[:16].replace("T", " ")
                    })
                st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
                
                comparable_runs = get_comparable_history_runs(filtered_runs)
                legacy_count = len(filtered_runs) - len(comparable_runs)
                if legacy_count:
                    st.info(
                        f"{legacy_count} Legacy- oder ungültige Benchmark-Einträge werden nicht "
                        "für Gewinner oder Aggregate verwendet."
                    )

                # Aggregated Statistics (requires >= 2 comparable runs)
                if len(comparable_runs) >= 2:
                    st.markdown("### 📊 Aggregierte Benchmark-Statistik")

                    comparable_summaries = [
                        get_history_objective_summary(r) for r in comparable_runs
                    ]
                    baselines = [s["baseline_distance_with_exit_m"] for s in comparable_summaries]
                    best_dists = []
                    differences_m = []
                    differences_pct = []
                    backtrackings_base = []
                    backtrackings_best = []
                    best_methods = []
                    improvement_count = 0
                    backtracking_fields = {
                        "Grouped Aisle": "grouped_backtracking_m",
                        "Greedy Nearest": "greedy_backtracking_m",
                        "End Aware": "end_aware_backtracking_m",
                        "Physical Aisle - Distance Optimum": "physical_distance_backtracking_m",
                        "Physical Aisle - Operational Optimum": "physical_operational_backtracking_m",
                    }
                    for r, objective_summary in zip(comparable_runs, comparable_summaries):
                        best_method_key = objective_summary["best_heuristic_method"]
                        best_methods.append(best_method_key)
                        best_val = objective_summary["best_heuristic_distance_with_exit_m"]
                        baseline_val = objective_summary["baseline_distance_with_exit_m"]
                        best_dists.append(best_val)
                        difference_m = baseline_val - best_val
                        differences_m.append(difference_m)
                        differences_pct.append(
                            (difference_m / baseline_val * 100) if baseline_val > 0 else 0.0
                        )
                        if objective_summary["heuristic_improves_baseline"]:
                            improvement_count += 1

                        baseline_backtracking = r.get("baseline_backtracking_m")
                        heuristic_backtracking = r.get(backtracking_fields[best_method_key])
                        if is_valid_objective_value(baseline_backtracking):
                            backtrackings_base.append(baseline_backtracking)
                        if is_valid_objective_value(heuristic_backtracking):
                            backtrackings_best.append(heuristic_backtracking)
                        
                    import statistics
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Ø Baseline – Distanz inklusive Ausgang", f"{statistics.mean(baselines):.2f} m")
                        st.metric("Ø beste Heuristik – Distanz inklusive Ausgang", f"{statistics.mean(best_dists):.2f} m")
                    with c2:
                        st.metric("Ø Differenz zur Baseline (m)", f"{statistics.mean(differences_m):.2f} m")
                        st.metric("Ø Differenz zur Baseline (%)", f"{statistics.mean(differences_pct):.1f}%")
                    with c3:
                        st.metric("Median Differenz zur Baseline (%)", f"{statistics.median(differences_pct):.1f}%")
                        st.metric("Heuristik verbessert Baseline", f"{improvement_count} von {len(comparable_runs)}")

                    st.caption("Positive Differenzwerte bedeuten eine Verbesserung gegenüber der Baseline.")
                    if improvement_count == 0:
                        st.warning("Keine getestete Heuristik verbessert die Baseline.")
                        
                    # Backtracking metrics
                    st.markdown("#### Backtracking-Vergleich")
                    c_bt1, c_bt2 = st.columns(2)
                    with c_bt1:
                        if backtrackings_base:
                            st.metric("Ø Backtracking (Baseline)", f"{statistics.mean(backtrackings_base):.2f} m")
                            st.metric("Median Backtracking (Baseline)", f"{statistics.median(backtrackings_base):.2f} m")
                    with c_bt2:
                        if backtrackings_best:
                            st.metric("Ø Backtracking (Beste Heuristik)", f"{statistics.mean(backtrackings_best):.2f} m")
                            st.metric("Median Backtracking (Beste Heuristik)", f"{statistics.median(backtrackings_best):.2f} m")
                        
                    # Method success counts
                    st.markdown("### Beste getestete Heuristik nach Distanz inklusive Ausgang")
                    best_counts = {}
                    for method in best_methods:
                        best_counts[method] = best_counts.get(method, 0) + 1
                        
                    df_counts = pd.DataFrame(list(best_counts.items()), columns=["Optimierungsmethode", "Häufigkeit"]).set_index("Optimierungsmethode")
                    st.bar_chart(df_counts)
                    for m, cnt in sorted(best_counts.items(), key=lambda x: x[1], reverse=True):
                        st.write(f"- **{m}:** {cnt} mal kürzeste getestete Heuristik")
                        
    with tab_sim:
        st.subheader("🎲 Synthetische Picklisten generieren")
        st.write("Generieren Sie zufällige, logistisch valide Testdaten, um die Heuristiken unter verschiedenen Verteilungsszenarien zu vergleichen.")
        
        num_sim_picks = st.slider("Anzahl Picks in der Simulation", min_value=5, max_value=100, value=30, step=5)
        
        # Select aisles to include
        selected_aisles = st.multiselect(
            "Physische Gänge für Simulation auswählen (leer lassen für alle):",
            options=list(range(1, 10)),
            default=list(range(1, 10)),
            format_func=lambda x: f"Gang {x} (Seiten {x*2:02d}/{x*2+1:02d})" if x < 9 else f"Gang 9 (Seite 20)"
        )
        
        include_cart = st.checkbox("Wagen-Picks (01-03) erlauben?", value=True)
        
        if st.button("Synthetische Batch erzeugen & speichern", key="generate_sim_batch_button"):
            import random
            
            # Map physical aisles to available sides
            aisle_sides = {}
            for a in range(1, 9):
                aisle_sides[a] = [a*2, a*2+1]
            aisle_sides[9] = [20]
            
            cart_sides = [1, 2, 3]
            
            allowed_sides = []
            aisles_to_use = selected_aisles if selected_aisles else list(range(1, 10))
            for a in aisles_to_use:
                allowed_sides.extend(aisle_sides[a])
                
            if include_cart:
                allowed_sides.extend(cart_sides)
                
            sim_codes = []
            for _ in range(num_sim_picks):
                side = random.choice(allowed_sides)
                row = random.randint(1, 84)
                box = random.randint(10, 90)
                sim_codes.append(f"{side:02d}.{row:03d}.{box:02d}")
                
            # Save synthetic batch
            new_sim_id = generate_next_batch_id(list(all_batches.keys()))
            new_sim_id = new_sim_id.replace("BATCH-", "SIM-")
            
            new_order = PickOrder(
                order_id=new_sim_id,
                timestamp_str=datetime.now().isoformat(),
                raw_picks_list=sim_codes,
                warehouse=warehouse,
                source="simulation"
            )
            
            try:
                save_batch(BATCHES_PATH, new_order)
                st.success(f"Synthetische Simulationsbatch **{new_sim_id}** mit {num_sim_picks} Picks erfolgreich erzeugt und gespeichert!")
                st.write("**Generierte Picks:**")
                st.write("; ".join(sim_codes))
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Generieren der Batch: {e}")

# ----------------------------------------------------
# Page 7: Einstellungen
# ----------------------------------------------------
elif navigation == "7. Einstellungen":
    st.markdown("<h1 class='main-header'>Einstellungen</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>System- und Simulationsparameter konfigurieren</p>", unsafe_allow_html=True)
    
    st.subheader("Picker Parameter (Simulation)")
    st.slider("Picker-Geschwindigkeit (m/s)", min_value=0.5, max_value=2.0, value=1.0, step=0.1)
    st.number_input("Sekunden pro Pick-Vorgang (Sek.)", min_value=1, max_value=60, value=15)
    st.button("Einstellungen Speichern")
