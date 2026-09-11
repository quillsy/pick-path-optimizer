# Arbeitsregeln für Coding-Agenten

Diese Vorgaben gelten dauerhaft für alle Arbeiten am Projekt "Pick Path Optimizer". Befolge diese Grundsätze stets konsequent und passe sie nicht eigenmächtig an.

## 1. Arbeitsweise
- **Zustand prüfen:** Analysiere vor jeder Änderung den aktuellen Branch, den HEAD, den Git-Status und die exakt betroffenen Dateien.
- **Minimalinvasive Änderungen:** Setze ausschließlich kleine, klar begrenzte Änderungen um. Vermeide ungefragte Gesamtumbauten (Refactorings).
- **Lokale Arbeit erhalten:** Bestehende uncommittete Änderungen des Nutzers sind zu schützen. Die Anweisung „Stoppen“ bedeutet exakt anhalten und berichten, nicht Arbeitsergebnisse „zurücksetzen“.
- **Formatierungsfehler:** Korrigiere eigene kleine Formatierungsfehler (wie Trailing Whitespaces) selbstständig im erlaubten Änderungsumfang und prüfe danach erneut, anstatt den Auftrag direkt abzubrechen.
- **Problem-Meldungen:** Findest du ein fachliches Problem außerhalb des expliziten Auftragsrahmens, nimm keine ungefragten Reparaturen vor, sondern melde den Befund übersichtlich im Abschlussbericht.

## 2. Daten und Routen
- **Originaltreue:** Die originale Batch-Reihenfolge, die Pick-Anzahl sowie eventuelle Duplikate in den Daten müssen stets strikt erhalten bleiben.
- **Kapselung:** Halte Datenimporte und die Logik des Routings stets sauber voneinander getrennt.
- **Datenschutz für `data/`:** Überschreibe, lösche oder erzeuge Dateien im Ordner `data/` unter keinen Umständen neu, es sei denn, ein ausdrücklicher Auftrag erfordert es.
- **Sicheres Testen:** Führe Experimente und Modultests mit temporären Datensätzen oder ausdrücklich nicht-persistierenden Aufrufen in isolierten Testumgebungen durch.
- **Keine Vermutungen:** Ergänze keine Lagermaße oder Pickkoordinaten aus eigenen theoretischen Vermutungen. Wenn Fakten fehlen, weise darauf hin.
- **Benchmarks einordnen:** Stelle ältere Benchmark-Zahlen nicht als bestätigte, reale Laufstrecken dar. Sie spiegeln nur den jeweiligen Entwicklungsstand der Modellierung wider.

## 3. Prüfungen und Git
- **Tests ausführen:** Verwende für Tests die Standardbibliothek, z.B. gezielt via `python -B -m unittest discover -s tests -p "<dateiname>.py" -v` oder vollständig via `python -B -m unittest discover -s tests -v`. Weitere Details findest du in `docs/testing.md`.
- **Isolierte Tests:** Befinden sich ungesicherte schützenswerte Arbeitsdaten im Verzeichnis, kopiere den für den Test benötigten Code in eine temporäre isolierte Kopie und führe den Test dort aus.
- **Striktes Staging:** Stage für einen Commit immer nur die ausdrücklich beauftragten und überprüften Dateien.
- **Commit-Prüfung:** Prüfe vor jedem Commit den tatsächlichen Diff und stelle sicher, dass `git diff --cached --check` fehlerfrei ist.
- **Begrenzte Git-Operationen:** Führe Commit, Push, Merge und Deployment ausschließlich im exakt freigegebenen Umfang aus.
- **Sicherheit:** Nimm niemals Zugangsdaten, Tokens oder private Pfade in den Code, in Remote-URLs oder in Abschlussberichte auf.
- **Abschlussberichte:** Nenne im Abschlussbericht kompakt die durchgeführten Änderungen, tatsächliche Testergebnisse, weiterhin bestehende Einschränkungen und (sofern zutreffend) echte, ungekürzte Commit- oder GitHub Actions Run-IDs aus den entsprechenden Befehlsausgaben.
