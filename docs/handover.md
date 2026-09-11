# Projekt-Übergabe: Pick Path Optimizer

## A. Bezugspunkt
Der in dieser Übergabe dokumentierte Stand der Prüfung bezieht sich auf:
- **Branch:** `feat/section-geometry-foundation`
- **Geprüfter Ausgangs-Commit:** `71b07911f8a5262aa6c7e191b9fa9140d8b0c5b1`

*(Dies ist der Stand zum Zeitpunkt der Erstellung dieser Dokumentation und nicht garantiert der dauerhaft aktuelle HEAD).*

## B. Orientierung im Projekt
Die nachfolgende Tabelle gibt einen kurzen Überblick über die wichtigsten vorhandenen Dateien und deren tatsächliche Aufgabe:

| Komponente | Datei(en) | Aufgabe |
|---|---|---|
| Warehouse-Modell | `modules/warehouse.py` | Datenhaltung für Lagerkonfiguration und physische Gänge, sowie Ableitung der Pickkoordinaten durch `Warehouse.get_coordinates()` |
| Neuer Abschnittsbaustein | `modules/section_geometry.py` | Basisberechnungen und Validierung der Regalgeometrie |
| Pick-Parsing und Speicherung | `modules/picks.py` | Zerlegt und validiert Pickcodes, ordnet Picks mithilfe des Warehouse-Modells räumlich zu und speichert bzw. lädt Batches. `save_batch()` speichert die Pickcodes in ihrer Reihenfolge und Batch-Metadaten. Es speichert keine eigene vollständige Koordinatentabelle. |
| Distanzberechnung | `modules/routing.py` | Logik zur Ermittlung der kürzesten Laufwege zwischen Picks |
| Optimierer | `modules/optimization.py` | `BaselineOptimizer`: unveränderte Eingabereihenfolge. `GroupedAisleOptimizer`, `GreedyNearestOptimizer`, `EndAwareOptimizer`: vorhandene Heuristiken. `PhysicalAisleDistanceOptimizer` und `PhysicalAisleOperationalOptimizer`: Varianten einer Richtungsenumeration bei vorgegebener Gangreihenfolge. **Die Enumeration untersucht Richtungsentscheidungen innerhalb des implementierten Suchraums, nicht sämtliche möglichen Gang- und Pickreihenfolgen. Sie ist kein allgemeiner TSP-Solver und kein Nachweis eines globalen Optimums.** |
| Benchmark | `modules/optimizer_benchmark.py` | Ausführung und Vergleich von Optimierungsläufen |
| Visualisierung | `visualization/warehouse_map.py` | Plotly-Lagerkarte und Darstellung der Wegpunkte |
| Streamlit-Oberfläche | `app.py` | Streamlit-Oberfläche und Aufruf der jeweiligen Funktionen |
| Testworkflow | `.github/workflows/python-tests.yml` | Automatisierte Testpipeline via GitHub Actions |

## C. Was erreicht wurde
- **Geometrie-Baustein:** Die Klasse `SectionGeometry` in `modules/section_geometry.py` berechnet und validiert die bestätigten Abschnittsgrenzen.
- **Integration:** Dieser Baustein ist weiterhin **nicht** in die laufende Routenberechnung oder Streamlit-Anwendung integriert.
- **Automatisierte Tests:** Eine automatische GitHub Actions Testpipeline läuft unter Python 3.12 und 3.13. (Beispielsweise zeigte Workflow Run `34655710697` einen erfolgreichen Durchlauf von 123 Tests pro Python-Version).
- **Datenkontrolle:** Die GitHub-Pipeline vergleicht verlässlich den Dateiendzustand von `data/`, sie überwacht jedoch nicht sämtliche zwischenzeitlichen Schreibzugriffe.

## D. Wichtigster offener Fehler
Drei betroffene Stellen berechnen fehlerhafte Laufstrecken:

1. **`Warehouse.get_coordinates()` in `modules/warehouse.py`:** Berechnet Pickkoordinaten. Für den ersten Abschnitt wird derzeit beispielsweise `(row - 0.5) * shelf_length_m` verwendet. Damit wird die Regallänge fälschlich als Schrittweite je Reihennummer behandelt.
2. **`calculate_distance_with_type()` in `modules/routing.py`:** Verwendet diese Pickkoordinaten und berechnet zusätzlich die Übergangspositionen aus derselben falschen Abschnittslänge.
3. **`generate_detailed_path_points()` und `draw_warehouse_map()` in `visualization/warehouse_map.py`:** Berechnen Wegübergänge beziehungsweise Regalabschnittsgrenzen ebenfalls mit dieser Längenannahme.

Gegenüberstellung:
- bisherige Annahme: 42 × 1,30 m = 54,60 m je Abschnitt
- bestätigte Messung: 7 × 1,30 m = 9,10 m je Abschnitt

Eine spätere Reparatur muss diese zusammengehörenden Berechnungen konsistent umstellen. Ein isolierter Austausch einer Formel genügt nicht. Verweise für die bestätigten Maße auf `docs/section_geometry.md`.

**Dabei ist zwingend zu beachten:**
- **19,63 m** beschreibt die Gesamtlänge beider Regalabschnitte einschließlich Mittelgang, aber **keine** vollständige Pickroute.
- Alle alten Meterwerte und Einsparungsprozente aus bisherigen Benchmarks sind **nicht** als reale Ergebnisse freigegeben.
- Es reicht nicht aus, die bisherigen Entfernungen einfach durch sechs zu teilen.
- Routing, Karte und Pickkoordinaten müssen im Rahmen einer künftigen Integration stattdessen gemeinsam auf eine einheitliche, bestätigte Geometrie umgestellt werden.

## E. Was für die Integration noch fehlt
Die Integration des Bausteins ist blockiert, bis folgende fachliche Fragen geklärt sind:
- Wie liegen die nummerierten Reihenpositionen tatsächlich innerhalb eines Regals?
- Welche Positionen erfordern eine Bewegung entlang des Ganges?
- Sind diese Abstände gleichmäßig?
- Wo liegen die relevanten Bezugspunkte für vorderen und hinteren Querweg?

Trage hierbei **kein** gleichmäßiges Raster von 9,10 m / 42 als Tatsache ein – das bloße Verhältnis beweist die räumliche Anordnung nicht. Der nächste fachliche Integrationsschritt beginnt erst nach bestätigter Positionszuordnung. Bis dahin können nur davon unabhängige Arbeiten separat beauftragt werden.

## F. Lokale Besonderheit
Im lokalen Arbeitsverzeichnis existiert eine uncommittete Modifikation an `data/benchmark_history.json`. Dies ist ein bekannter lokaler Zustand, der bei einem frischen Klonen des Repositorys auf anderen Rechnern nicht automatisch vorliegt. Jeder neue Agent muss daher vor Arbeitsbeginn seinen eigenen Git-Status prüfen.
