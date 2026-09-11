# Bestätigte Abschnittsgeometrie – Baustein-Dokumentation

## Herkunft der Maße

Die folgenden Angaben stammen ausschließlich aus Nutzermessungen am realen Lager.
Sie wurden nicht aus vorhandenen Code-Annahmen abgeleitet.

| Eigenschaft | Bestätigter Wert | Quelle |
|---|---:|---|
| Länge eines Regals entlang des Laufwegs | 1,30 m | Nutzermessung |
| Regale hintereinander je Regalabschnitt | 7 | Nutzermessung |
| Freie Breite des Mittelgangs (Quergang) | 1,43 m | Nutzermessung |

Beide Regalabschnitte (Reihen 001–042 bzw. 043–084) haben dieselbe Anzahl Regale
und damit dieselbe physische Länge.

---

## Koordinatenkonvention dieses Bausteins

```
y = 0  →  vordere Kante des ersten Regalabschnitts
```

Diese Konvention ist eine geometrische Referenz. Sie beschreibt **nicht** die
Wegmittellinie des vorderen Quergangs und ist kein Fachmittelpunkt von Reihe 001.

---

## Berechnete Abschnittsgrenzen

Alle Werte werden aus den drei Eingaben abgeleitet. Keine festen Ergebniswerte
im Produktionscode.

| Eigenschaft | Formel | Wert |
|---|---|---:|
| Länge eines Regalabschnitts | 7 × 1,30 m | **9,10 m** |
| Beginn Abschnitt 1 (Konventionsursprung) | — | **0,00 m** |
| Ende Abschnitt 1 / Beginn Mittelgang | 0,00 + 9,10 | **9,10 m** |
| Geometrische Mitte des Mittelgangs | 9,10 + 1,43 / 2 | **9,815 m** |
| Ende Mittelgang / Beginn Abschnitt 2 | 9,10 + 1,43 | **10,53 m** |
| Ende Abschnitt 2 | 10,53 + 9,10 | **19,63 m** |
| Gesamtlänge beider Abschnitte + Mittelgang | 9,10 + 1,43 + 9,10 | **19,63 m** |

---

## Öffentliche Schnittstelle

```python
from modules.section_geometry import SectionGeometry

geom = SectionGeometry(
    shelf_length_m=1.30,
    shelves_per_section=7,
    cross_aisle_width_m=1.43,
)

geom.section_length_m       # 9.10
geom.section1_start_m       # 0.00
geom.section1_end_m         # 9.10
geom.cross_aisle_start_m    # 9.10  (Alias)
geom.cross_aisle_centre_m   # 9.815
geom.cross_aisle_end_m      # 10.53
geom.section2_start_m       # 10.53 (Alias)
geom.section2_end_m         # 19.63
geom.total_length_m         # 19.63
```

`SectionGeometry` ist ein `@dataclass(frozen=True)` und damit unveränderlich (immutable).

---

## Weiterhin ungeklärt: Zuordnung der Reihennummern

Folgendes ist durch diesen Schritt **nicht** festgelegt worden und darf
noch nicht in Routenberechnungen eingebaut werden:

- Wie die 42 Reihennummern (001–042) auf Positionen innerhalb eines
  Regalabschnitts von 9,10 m verteilt sind.
- Ob der Reihenabstand konstant ist.
- Ob Reihe 001 exakt an der vorderen Regalabschnittskante liegt.
- Ob Reihe 084 exakt an der hinteren Regalabschnittskante liegt.
- Wo genau sich die Wegmittellinien des vorderen und hinteren Quergangs
  befinden (sie liegen nicht zwingend auf einer Regalabschnittskante).

> **Regallänge**, **Regaltiefe**, **Fachmittelpunkt** und
> **Wegmittellinie** sind unterschiedliche physische Größen.

---

## Integrationsstatus

> **⚠ Dieser Baustein ist noch nicht in die laufende Anwendung eingebunden.**

Die folgenden Module wurden in diesem Schritt **nicht verändert**:

- `modules/warehouse.py`
- `modules/routing.py`
- `modules/optimization.py`
- `modules/optimizer_benchmark.py`
- `visualization/warehouse_map.py`
- `app.py`

**Die bestehende Routenberechnung ist durch diesen Schritt noch nicht repariert.**  
Die bisherigen Meterangaben (z. B. Baseline 935,59 m für BATCH-HISTORICAL-0001)
sind weiterhin nicht als bestätigte reale Laufstrecken freigegeben.

---

## Testabdeckung

```
tests/test_section_geometry.py
```

Die Tests prüfen ausschließlich `SectionGeometry`. Sie importieren weder
`warehouse.json` noch die bestehende Warehouse-, Routing- oder
Benchmark-Logik.
