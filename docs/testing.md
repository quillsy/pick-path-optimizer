# Test-Pipeline

Diese Dokumentation beschreibt den automatisierten GitHub Actions Testworkflow (`Python tests`) für das Projekt Pick Path Optimizer.

## Zweck und Auslöser
Der Workflow führt automatisch die vollständige Testsuite des Projekts in frischen, isolierten Umgebungen aus.
Ausgelöst wird die Pipeline bei:
- Push auf den Branch `feat/section-geometry-foundation`
- Push auf den Branch `main`
- Pull Requests mit Zielbranch `main`

## Getestete Python-Versionen
Die Testsuite wird in einer Matrix über folgende Versionen ausgeführt, um die Kompatibilität zu sichern:
- Python 3.12
- Python 3.13

*(Diese Versionen beziehen sich ausschließlich auf den Test-Runner, nicht zwingend auf die lokale UI-Umgebung).*

## Ausgeführter Testbefehl
Der Workflow verwendet die Python-Standardbibliothek zur Ausführung aller Tests:
```bash
python -B -m unittest discover -s tests -v
```

## Ergebnisse einsehen
Die Ergebnisse aller Testläufe können direkt auf GitHub im Repository unter dem Tab **"Actions"** eingesehen werden.

## Untersuchung fehlgeschlagener Tests
1. Navigiere auf GitHub zum **"Actions"**-Tab.
2. Wähle den fehlgeschlagenen Workflow-Lauf aus.
3. Klicke auf den fehlgeschlagenen Job (z.B. Python 3.12).
4. Klappe den Schritt **"Run tests"** (bzw. den betroffenen Schritt) auf, um den genauen Traceback und die Fehlermeldung zu analysieren.

## Daten-Endzustandsprüfung
Nach jedem Testlauf findet eine Überprüfung der Dateiinhalte unter `data/` statt. Dies stellt sicher, dass die Tests die zugrundeliegenden Referenzdaten nicht permanent überschreiben oder löschen. Es handelt sich hierbei um eine **Prüfung des Endzustands** nach dem Testdurchlauf, keine Überwachung sämtlicher zwischenzeitlicher Schreibzugriffe. Eine Abweichung zum Startzustand führt zum Fehlschlag des Jobs.

> **Wichtige Einschränkung:**
> Grüne Tests bestätigen die vorhandenen automatischen Prüfungen. Sie bestätigen weder die reale Lagergeometrie noch eine fehlerfreie Streamlit-Oberfläche. Die Reihenpositionen sind weiterhin ungeklärt und der Abschnittsbaustein ist noch nicht integriert.
