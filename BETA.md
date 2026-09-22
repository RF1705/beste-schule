# Beta 1.0.4-beta.1: WÜ/TÜ im Arbeiten-Kalender

Diese Beta ergänzt die Erkennung von WÜ/TÜ und hilft bei der Suche nach weiterhin fehlenden Terminen. Ob die Schule die Angaben in den von uns gelesenen API-Feldern liefert, muss mit einem echten Termin geprüft werden.

## Installation

Das vorbereitete ZIP enthält den Inhalt des Integrationsordners. Für eine manuelle Installation die Dateien nach `config/custom_components/beste_schule/` entpacken und die vorhandenen Integrationsdateien ersetzen. Danach Home Assistant neu starten. Die bestehende Einrichtung bleibt erhalten.

Die Beta ist als GitHub-Vorabversion verfügbar: https://github.com/RF1705/beste-schule/releases/tag/v1.0.4-beta.1. In HACS gegebenenfalls Vorabversionen einblenden und Version `1.0.4-beta.1` auswählen.

## Gezielt testen

1. In den Optionen der Integration prüfen, dass der Arbeiten-Kalender aktiviert ist, und ihn in der Kalenderansicht auswählen.
2. Einen WÜ/TÜ-Termin auswählen, der in beste.schule sichtbar ist. Für den ersten Test einen Termin in den nächsten sieben Tagen verwenden.
3. Unter **Einstellungen → Geräte & Dienste → beste.schule** im Menü **Debug-Protokollierung aktivieren** wählen.
4. Einen regulären Datenabruf abwarten (bis zu 15 Minuten). Danach die Kalenderansicht mit dem betroffenen Tag erneut öffnen.
5. Prüfen, ob der Termin jetzt erscheint. Anschließend Debug-Protokollierung deaktivieren und das angebotene Protokoll herunterladen.
6. Für die Auswertung nur die Zeilen mit `Exam diagnostics:` heraussuchen. Dazu angeben, ob der Termin erschienen ist und wie der Typ in beste.schule heißt, beispielsweise „WÜ“. Keine Namen oder vollständigen Schulnotizen nötig.

Die neuen Diagnosezeilen enthalten je Quelle (`journal_lessons`, `journal_weeks`, `journal_lesson_student`):

- `status`: Quelle vorhanden (`ok`), nicht vorhanden (`missing`) oder API-Fehler (`error`).
- `selected`: Wird diese Quelle tatsächlich für den Arbeiten-Kalender verwendet?
- `counts`: Zahl der Notizen und Gründe für ihre Behandlung: `unrecognized`, `missing_date`, `outside_requested_range`, `source_not_selected`, `accepted_before_deduplication`. Zusätzlich werden fehlende Typnamen und unerwartete Datenformen gezählt.
- `markers`: Häufigkeit fest definierter Erkennungsbegriffe wie `wü` oder `tü`. Unbekannte Typnamen und Freitexte werden nicht ausgegeben.

Es handelt sich um Zähler aus der verschachtelten API-Struktur, nicht zwingend um die Anzahl eindeutiger Termine. Die Zusammenfassung wird bei Kalenderabfragen erzeugt und kann deshalb mehrfach erscheinen. Im gesamten Home-Assistant-Protokoll können andere Komponenten persönliche Daten ausgeben; für die Rückmeldung reichen die genannten Diagnosezeilen.

## Noch offen

Die Beta ändert die Auswahl der Journal-Quelle nicht. Ein Treffer mit `source_not_selected` zeigt uns, ob weitere Quellen berücksichtigt werden müssen. Auch Unterrichtsausfall wird damit noch nicht anders dargestellt.
