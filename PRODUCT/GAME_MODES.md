# GAME MODES

## Deutsch ist einfach! — Quiz Arena

**Sprache:** Deutsch (Bot-UI & Dokumentation) — **STRICT**

---

## 1. Ziel dieses Dokuments

Dieses Dokument definiert **alle Spielmodi** von *Deutsch ist einfach! — Quiz Arena*.

Ziel ist:

* eindeutige Regeln pro Modus
* keine Interpretationsfreiheit für Entwickler
* konsistentes Spielerlebnis
* Skalierbarkeit für zukünftige Erweiterungen

Dieses Dokument folgt strikt:

* `PRODUCT_VISION.md`
* `AGENT_CONSTITUTION.md`
* `UX_FLOW.md`

---

## 2. Grundprinzipien für alle Spielmodi

Diese Regeln gelten **für jeden Modus ohne Ausnahme**:

1. **Skill-based** – kein Zufall über Sieg/Niederlage
2. **Anti-Repeat** – keine identische Frage innerhalb der Cooldown-Zeit
3. **Anti-Pattern** – keine identischen Fragetypen hintereinander
4. **Kurz & fokussiert** – Sessions dauern max. 2–5 Minuten
5. **Sofortiges Feedback** – jede Antwort hat klares Resultat
6. **Eine klare nächste Aktion** – nie Sackgassen im Flow

---

## 3. Kategorie A — Free Games (Entry Layer)

### 3.1 Quick Mix (A1 / A2)

**Zweck:** Soforterlebnis, Einstieg, tägliche Nutzung

**Regeln:**

* Fragen: 5
* Niveau: A1 oder A2
* Themen: gemischt
* Zeitlimit: keins
* Teilnahme: unbegrenzt

**Scoring:**

* 1 Punkt pro richtige Antwort
* Zeit spielt keine Rolle

**Besonderheiten:**

* Standardmodus für neue Nutzer
* Wird für Challenge-Generierung verwendet

---

### 3.2 Mini-Spiele

**Zweck:** Fokus auf typische Fehler, hoher Aha-Effekt

**Verfügbare Mini-Spiele:**

* der/die/das Sprint
* Wortstellung Blitz
* Trennbare Verben
* Akkusativ/Dativ Mini

**Regeln:**

* Fragen: 5
* Ein Thema pro Session
* Sehr kurze Erklärungen (max. 1 Satz)

---

### 3.3 Endless Lite

**Zweck:** Spaß + Motivation ohne Druck

**Regeln:**

* Spiel endet nach 2 falschen Antworten
* Max. 1 Session pro Tag
* Schwierigkeit steigt leicht

**Scoring:**

* Gesamtzahl richtiger Antworten

---

### 3.4 Daily Challenge

**Zweck:** Retention, Streak-Aufbau

**Regeln:**

* Fragen: 7
* Gleicher Satz für alle Nutzer pro Tag
* 1 Teilnahme pro Tag

**Scoring:**

* Anzahl korrekter Antworten

---

## 4. Kategorie B — Skill Games (Progress Layer)

### 4.1 Topic Run

**Zweck:** gezieltes Training

**Regeln:**

* Fragen: 10–15
* Nutzer wählt Thema
* Schwierigkeit passt sich an

**Unlock:**

* via Aktivität oder Paket

---

### 4.2 Smart Mix

**Zweck:** Anti-Langeweile, ganzheitliches Training

**Regeln:**

* 10 Fragen
* 3–4 Fragetypen
* keine zwei gleichen Typen hintereinander

---

### 4.3 Exam Mode

**Zweck:** Prüfungssimulation

**Regeln:**

* Fragen: 20–25
* Zeitlimit aktiv
* Keine Erklärungen während des Spiels

**Scoring:**

* Punkte + Zeit als Tie-Break

---

### 4.4 Endless Pro

**Zweck:** Langzeitspiel für Power User

**Regeln:**

* Spiel endet nach 3 Fehlern
* Keine Tageslimits
* Schwierigkeit steigt deutlich

---

## 5. Kategorie C — Tournament Games

### 5.1 Allgemeine Turnierregeln

* Identische Fragen für alle Teilnehmer
* Fixierter Seed pro Turnier
* Zeitlimit aktiv
* Deterministische Auswertung

---

### 5.2 Sit & Go Turnier

**Zweck:** schnelle Wettbewerbe

**Regeln:**

* Spieler: 5–20
* Fragen: 10
* Dauer: ca. 5 Minuten

---

### 5.3 Daily Turnier

**Regeln:**

* 1 Start pro Tag
* Fragen: 20
* Offene Teilnehmerzahl

---

### 5.4 Weekly Main Event

**Regeln:**

* 1 Start pro Woche
* Fragen: 30–40
* Erhöhte Schwierigkeit

---

### 5.5 Monthly Championship

**Regeln:**

* Zugang nur über Qualifikation
* Höchste Schwierigkeit
* Limitierte Teilnehmerzahl

---

## 6. Scoring & Tie-Break Regeln

1. Anzahl korrekter Antworten
2. Gesamtzeit
3. Weniger falsche Antworten
4. Gleichstand → gleicher Rang

---

## 7. Challenge Integration

* Jeder Modus (außer Exam Mode) kann Challenge erzeugen
* Challenge nutzt exakt dieselben Fragen
* Challenge ist zeitlich limitiert

---

## 8. Anti-Abuse Regeln

* Kein mehrfaches Spielen derselben Session
* Geräte-Fingerprint (sofern möglich)
* Verdächtige Muster → Shadow Cooldown

---

## 9. Erweiterbarkeit

Neue Modi müssen:

* einer Kategorie zugeordnet sein
* UX-Regeln einhalten
* Anti-Repeat respektieren

---

## 10. Definition of Done — Game Modes

Dieses Dokument ist DONE wenn:

* jeder Modus klar definiert ist
* keine Überschneidungen bestehen
* Entwickler keine Rückfragen stellen müssen
* alle Modi mit UX_FLOW kompatibel sind

---

## 11. Open Topics (spätere Slices)

* Adaptive Difficulty Algorithmen
* Audio-basierte Modi
* Team-basierte Turniere
