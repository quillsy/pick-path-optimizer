# Pick Path Optimizer - Schritt 1

Dieses Projekt dient der mathematischen Analyse und Laufwegoptimierung in der Lagerlogistik. In diesem ersten Schritt wurde die saubere technische Grundlage mit Python und Streamlit geschaffen.

## Features in Schritt 1
- **Lagerhaus-Modellierung:** Zentrale Konfiguration der physischen Gänge (Aisles), Stellplatzseiten, Regalmaße und Quergänge über eine strukturierte `data/warehouse.json`.
- **Parsing von Pick-Codes:** Zerlegung von Pick-Codes im Format `XX.YYY.ZZ` (z.B. `19.015.20` in Seite `19`, Reihe `15`, Fach/Box `20`). Führende Nullen werden korrekt verarbeitet.
- **Berechnung von Laufwegen:** Mathematische Berechnung des kürzesten Fußwegs unter Berücksichtigung der physischen Struktur (Gassen und 3 Quergänge: Oben, Mitte, Unten).
- **Interaktive Lagerkarte:** 2D-Darstellung des Lagers inklusive Gassen, Wagen (01-03) und animierter Pick-Routen über Plotly.
- **Routen-Heuristik:** Vergleich zwischen der originalen Scan-Reihenfolge und einer einfachen S-Shape-Gassensortierung.

## Projektstruktur
```
pick_path_optimizer/
├── app.py                      # Streamlit Hauptanwendung
├── data/
│   ├── warehouse.json          # Lager-Geometriedaten
│   └── pick_orders.csv         # Erste Mock-Pick-Batches
├── modules/
│   ├── warehouse.py            # Klassen für Lager & Gänge
│   ├── picks.py                # Pick- und Order-Parsing
│   └── routing.py              # Distanzberechnung & Basis-Routing
├── visualization/
│   └── warehouse_map.py        # Zeichnen der interaktiven Plotly-Karte
├── tests/
│   └── test_parsing.py         # Unit Tests für das Parsing
└── README.md                   # Diese Anleitung
```

## Installation & Start

### 1. Python-Abhängigkeiten installieren
Für das Projekt werden `streamlit`, `plotly` und `pandas` benötigt. Installieren Sie diese über `pip`:

```bash
pip install streamlit plotly pandas
```

### 2. Streamlit Anwendung starten
Navigieren Sie in das Projektverzeichnis und starten Sie die App:

```bash
streamlit run app.py
```

### 3. Unit Tests ausführen
Um die korrekte Funktionsweise des Pick-Parsings zu validieren:

```bash
python3 -m unittest tests/test_parsing.py
```
