# TOURNAMENT ENGINE

## Deutsch ist einfach! — Quiz Arena

**Sprache:** Deutsch (Bot-UI & Dokumentation) — STRICT

---

## 1. Zweck dieses Dokuments

Dieses Dokument definiert:

* Lebenszyklus eines Turniers
* Teilnehmerlogik
* Start- und Abschlussregeln
* Ranking-System
* Belohnungsmechanik (nicht-monetär)
* Anti-Abuse-Mechanismen

Dieses Dokument ist verbindlich für jede Implementierung.

---

## 2. Grundprinzipien

1. Turniere sind **skill-based Wettbewerbe**.
2. Keine Stars- oder Geldpreise.
3. Alle Teilnehmer erhalten identische Fragen.
4. Bewertung ist deterministisch.
5. Transparente Regeln ohne Interpretationsspielraum.

---

## 3. Turnier-Typen

### 3.1 Sit & Go

* Startet automatisch bei Mindestanzahl Teilnehmer (z. B. 5)
* Maximalteilnehmer: 20
* Fragen: 10
* Zeitlimit pro Frage: 15 Sekunden
* Gesamtdauer: ca. 5 Minuten

---

### 3.2 Daily Turnier

* 1 Start pro Kalendertag
* Offene Teilnehmerzahl
* Fragen: 20
* Zeitlimit pro Frage: 20 Sekunden
* Ranking wird um 23:59 fixiert

---

### 3.3 Weekly Main Event

* 1 Turnier pro Woche
* Fester Startzeitpunkt
* Fragen: 30–40
* Zeitlimit aktiv
* Erhöhte Schwierigkeit

---

### 3.4 Monthly Championship

* Zugang nur via Qualifikation oder Einladung
* Limitierte Teilnehmerzahl
* Höchste Schwierigkeit
* Längere Dauer

---

## 4. Turnier-Lifecycle

Jedes Turnier durchläuft folgende Zustände:

1. **Ankündigung**

   * Sichtbar im Lobby-Menü
   * Zeigt Startzeit und Teilnehmerzahl

2. **Registrierung**

   * Nutzer klickt „Teilnehmen“
   * Teilnahme wird gespeichert

3. **Start**

   * Seed wird generiert
   * Fragenpool fixiert
   * Kein späterer Einstieg möglich

4. **Aktive Phase**

   * Teilnehmer beantworten Fragen
   * Antworten werden sofort gespeichert

5. **Abschluss**

   * Ranking wird berechnet
   * Tie-Break-Regeln angewendet

6. **Belohnung**

   * Badges vergeben
   * Zugang oder Free Entries aktiviert

---

## 5. Frage-Selektion

* Ein globaler Seed pro Turnier
* Anti-Repeat global aktiv
* Keine identischen Fragetypen hintereinander
* Schwierigkeit entsprechend Turnier-Typ

---

## 6. Scoring-System

Primäre Sortierung:

1. Anzahl korrekter Antworten
2. Gesamtzeit
3. Weniger falsche Antworten

Bei vollständigem Gleichstand:

* gleicher Rang
* identische Belohnung

---

## 7. Ranking-System

### 7.1 Turnier-Ranking

* Sichtbar nach Abschluss
* Zeigt:

  * Rang
  * Punkte
  * Zeit

### 7.2 Globale Wertung (optional späterer Slice)

* Punkte pro Turnier
* Saison-Ranking

---

## 8. Belohnungssystem (Hybrid, nicht-monetär)

Mögliche Belohnungen:

* Temporärer Premium-Zugang
* Free Turnier-Entries
* Exklusive Badges
* Zugang zu geschlossenen Events

Belohnungen dürfen nie:

* in Stars umgewandelt werden
* handelbar sein
* monetären Gegenwert haben

---

## 9. Anti-Abuse Mechanismen

* Ein Account pro Turnier
* Kein erneutes Starten nach Abbruch
* Geräte- oder Verhaltensanalyse (falls möglich)
* Verdächtige Muster → Shadow-Bann für Turniere

---

## 10. Fairness-Regeln

* Alle Fragen werden serverseitig festgelegt
* Zeitmessung serverseitig
* Keine clientseitige Manipulation möglich

---

## 11. UI-Verhalten während Turnier

* Klare Anzeige „Turnier-Modus aktiv“
* Fortschrittsanzeige
* Keine Ablenkungen
* Keine externe Navigation

---

## 12. Definition of Done — Tournament Engine

Das Tournament Engine Dokument ist DONE wenn:

* Lifecycle vollständig definiert ist
* Scoring eindeutig ist
* Belohnungen klar abgegrenzt sind
* Anti-Abuse Regeln implementierbar sind
* Kein monetäres Risiko besteht

---

## 13. Erweiterbarkeit

Spätere Erweiterungen möglich:

* Team-Turniere
* Saison-System
* Elo-ähnliche Wertung
* Einladungsturniere

Diese dürfen nur in neuen Slices ergänzt werden.
