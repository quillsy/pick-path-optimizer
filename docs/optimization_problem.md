# Spezifikation des Routen-Optimierungsproblems (Pick Path Optimization)

Diese Dokumentation beschreibt die formalen mathematischen und physischen Regeln zur Routenoptimierung im Lager des Pick Path Optimizers. Sie dient als theoretische Grundlage für die zukünftige Implementierung von Optimierungsalgorithmen (wie Nearest Neighbor, TSP-Heuristiken, Genetische Algorithmen, etc.).

---

## 🎯 1. Zielgröße (Objective Function)

Das primäre Ziel ist die Minimierung der tatsächlichen Laufstrecke des Kommissionierers (Picker) in Metern.

### Mathematische Formulierung
Die Gesamtkosten einer Route (Total Cost) werden wie folgt berechnet:

\[\text{Total Cost} = D_{\text{start}} + \sum_{i=1}^{N-1} d(P_i, P_{i+1}) + D_{\text{end}}\]

Wobei:
*   \(d(P_i, P_{i+1})\): Die kürzeste Wegenetz-Distanz zwischen Pick \(P_i\) und Pick \(P_{i+1}\) (entlang der zugelassenen Korridore und Regalgassen, berechnet mittels `calculate_distance()`).
*   \(D_{\text{start}}\): Der Weg vom Startpunkt zum ersten Pick \(P_1\). Für die Standard-Baseline ist \(D_{\text{start}} = 0\), da die Route beim ersten Pick der Batch beginnt.
*   \(D_{\text{end}}\): Der Weg vom letzten Pick \(P_N\) zum Abstellbereich am Ausgang (Gang 20, Reihe 001).

---

## 🏃 2. Start- und Endbedingungen

### Startpunkt
Es gibt keinen festen Startpunkt (wie Gang 4). Der Startpunkt wird **flexibel durch den ersten Pick** der eingegebenen Batch bestimmt:
*   Wenn erster Pick bei Seite 01–03 liegt \(\rightarrow\) Start auf Wagen-Position bei Koordinate \((1,25\,\text{m}, -1,0\,\text{m})\).
*   Wenn erster Pick in einem Regal liegt \(\rightarrow\) Start direkt an dieser Regalposition.

### Endpunkt & Abstellbereich (Gang-20-Regel)
Nach dem letzten Pick läuft der Picker zum **Abstellbereich** (neben Reihe 001 an Gang 20).
*   **Logistische Regel:** Um Laufwege zu sparen, soll die Route idealerweise so enden, dass der Picker durch den einseitigen **Gang 9 (Stellplatzseite 20)** in Richtung Reihe 001 herausläuft.
*   **Reihenfolge in Gang 20:** Falls Picks in Gang 20 vorhanden sind, sollten diese vorzugsweise so sortiert werden, dass man sich von der größten Reihennummer (z. B. Reihe 080) hinunter zu kleineren Reihennummern (z. B. Reihe 020) vorarbeitet.
*   **Wichtig:** Es darf **kein künstlicher Pick** in Gang 20 erzeugt werden. Hat eine Batch keine Picks in Gang 20, läuft der Picker vom letzten Pick der Route auf dem kürzesten Wegenetz-Pfad zum Abstellbereich.

---

## 🏢 3. Physische Lagerstruktur & Wegenetz-Restriktionen

Der Picker darf sich **ausschließlich auf den Laufwegen** bewegen. Ein diagonales Durchqueren von Regalkörpern (Luftlinie / Euklidische Distanz) ist verboten.

### Die 9 physischen Gänge (Aisles)
Gegenüberliegende Stellplatzseiten gehören zum selben physischen Gang und müssen als **einzelner physischer Arbeitsbereich** behandelt werden:
1.  **Gang 1:** Seite 04 (links) / Seite 05 (rechts)
2.  **Gang 2:** Seite 06 (links) / Seite 07 (rechts)
3.  **Gang 3:** Seite 08 (links) / Seite 09 (rechts)
4.  **Gang 4:** Seite 10 (links) / Seite 11 (rechts)
5.  **Gang 5:** Seite 12 (links) / Seite 13 (rechts)
6.  **Gang 6:** Seite 14 (links) / Seite 15 (rechts)
7.  **Gang 7:** Seite 16 (links) / Seite 17 (rechts)
8.  **Gang 8:** Seite 18 (links) / Seite 19 (rechts)
9.  **Gang 9 (einseitig):** Seite 20 (links) / rechts keine Regale

Zusätzlich gibt es den **Wagen** an der Wand (neben Stellplatzseite 04) mit den Sonderseiten 01, 02 und 03.

### Die 3 erlaubten Quergänge (Übergänge)
Ein Wechsel zwischen verschiedenen physischen Gängen ist ausschließlich an folgenden drei Stellen erlaubt:
1.  **Eingangsbereich bei Reihe 001 (unten):** Koordinate \(y = 0,0\,\text{m}\).
2.  **Mittel-/Quergang zwischen Reihe 042 und 043 (Mitte):** Breite 1,43 m, Koordinate \(y \approx 55,32\,\text{m}\).
3.  **Ausgangsbereich bei Reihe 084 (oben):** Koordinate \(y \approx 110,63\,\text{m}\).

---

## 📦 4. Boxnummern & Pick-Gruppierung
Die Boxnummer (die dritte Zahl im Pick-Code, z. B. `.50` in `05.056.50`) hat **keinen Einfluss** auf die physische Koordinate des Picks im 2D-Raum.
*   Mehrere Picks an derselben Seite und Reihe (z. B. `05.056.10` und `05.056.50`) verweisen auf **dieselbe Koordinate** (x, y).
*   Die Distanz zwischen solchen identischen Lagerplatz-Picks beträgt \(0,0\,\text{m}\).
*   Sie dürfen **nicht** herausgefiltert oder zusammengelegt werden (Reihenfolge und Duplikate bleiben erhalten).

---

## 🔄 5. Mathematische Definition von „Unnötigem Zurücklaufen“ (Backtracking)

Backtracking tritt auf, wenn ein Picker eine bereits durchlaufene Gassenstrecke in entgegengesetzter Richtung erneut betreten muss, um einen ausgelassenen Pick einzusammeln.

### Mathematischer Nachweis über Wegsegmente
Sei \(P_1(y_1)\), \(P_2(y_2)\) und \(P_3(y_3)\) eine dreigliedrige Pick-Sequenz innerhalb **desselben physischen Ganges** (Aisle ID \(A\)), die nacheinander abgearbeitet wird.

Ein unnötiges Zurücklaufen (Backtracking) liegt vor, wenn:
1.  Die Bewegungsrichtung auf der y-Achse wechselt:
    \[\operatorname{sgn}(y_2 - y_1) \neq \operatorname{sgn}(y_3 - y_2) \quad \text{und} \quad y_1 \neq y_2, \, y_2 \neq y_3\]
2.  Sich die y-Intervalle überschneiden:
    Das Intervall der zweiten Bewegung \(I_2 = [\min(y_2, y_3), \max(y_2, y_3)]\) schneidet das Intervall der ersten Bewegung \(I_1 = [\min(y_1, y_2), \max(y_1, y_2)]\) in mehr als einem Punkt:
    \[\text{Länge}(I_1 \cap I_2) > 0\]

#### Beispiel
*   **Ineffizient:** \(P_1 = 04.002\) (y=1.95) \(\rightarrow\) \(P_2 = 04.070\) (y=91.78) \(\rightarrow\) \(P_3 = 04.015\) (y=18.85).
    *   Erster Weg: \(1.95 \rightarrow 91.78\). Zweiter Weg: \(91.78 \rightarrow 18.85\).
    *   Richtungswechsel liegt vor (hoch, dann runter).
    *   Überlappungsbereich: \([18.85, 91.78]\) (Länge = 72,93 m). Der Picker läuft diesen Bereich zweimal ab.
*   **Effizient:** \(P_1 = 04.002\) \(\rightarrow\) \(P_2 = 04.015\) \(\rightarrow\) \(P_3 = 04.070\).
    *   Erster Weg: \(1.95 \rightarrow 18.85\). Zweiter Weg: \(18.85 \rightarrow 91.78\).
    *   Kein Richtungswechsel (stetig aufsteigend). Überlappung ist 0.

---

## 📊 6. Zukünftig zu messende Metriken

Um alternative Algorithmen vergleichen zu können, bereitet das Datenmodell folgende Metriken vor:
1.  **Gesamtstrecke (total_distance_m):** Die Summe aller Segmentdistanzen.
2.  **Anzahl physischer Gänge:** Anzahl der verschiedenen Gänge (1 bis 9), die betreten wurden.
3.  **Anzahl Gangwechsel (Aisle Crossings):** Wie oft wechselt die Route zwischen unterschiedlichen physischen Gängen.
4.  **Wechsel-Typen:**
    *   `crossings_via_001`: Anzahl der Wechsel über den Eingang (Reihe 001).
    *   `crossings_via_middle`: Anzahl der Wechsel über den Mittelgang.
    *   `crossings_via_084`: Anzahl der Wechsel über den Ausgang (Reihe 084).
5.  **Richtungswechsel (Direction Changes):** Wie oft ändert sich das Vorzeichen der y-Bewegung innerhalb der Gänge.
6.  **Backtracking-Ereignisse:** Anzahl der mathematisch erkannten überlappenden Rückwärtsbewegungen.
7.  **Endposition-Entfernung:** Die Distanz vom letzten Pick der Route zum Abstellbereich bei Gang 20 Reihe 001.
