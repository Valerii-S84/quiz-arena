# UX FLOW

## Deutsch ist einfach! — Quiz Arena (Telegram Bot)

**Sprache:** Deutsch (Bot-UI) — **STRICT**

---

## 1. UX-Ziele

1. **Time-to-First-Answer ≤ 20 Sekunden** nach /start
2. **Keine Überforderung:** Progressive Freischaltung statt großer Menüs
3. **Suchtfaktor:** kurze Sessions, sofortiges Feedback, klare nächste Aktion
4. **Virales Verhalten:** Challenge + Share sind Standard nach jeder Session
5. **Retention:** Daily Challenge + Streak als tägliche Gewohnheit

---

## 2. Grundprinzip: Progressive Freischaltung

Die sichtbaren Menüpunkte hängen von:

* Aktivität (Spiele gesamt)
* Streak (Tage)
* Teilnahme an Challenges/Tournaments
* Optional: Kaufstatus (Pakete), **aber niemals** als Voraussetzung für Grundfunktionen

**Regel:** Neue Nutzer sehen am Anfang nur das Nötigste.

---

## 3. Start & Onboarding

### 3.1 /start — First Session (Day 0)

**Bot sendet (Message 1):**

* Kurze Begrüßung (1 Zeile)
* 1 Satz: „Du lernst Deutsch durch ein Spiel. Schnell. Einfach. Jeden Tag.“
* CTA Button: **„▶️ Jetzt spielen“**

**Buttons (Inline):**

* ▶️ Jetzt spielen
* 🔥 Daily Challenge
* 🎁 Freund einladen
* ℹ️ Hilfe

**Wichtig:** Keine Pakete, keine Turniere, keine Statistik.

---

### 3.2 First Question Flow

Nach Klick auf „▶️ Jetzt spielen“ startet sofort:

**Session: Quick Mix (A1) — 5 Fragen**

* Progress-Bar: „Frage 1/5“
* Antwort-Buttons A/B/C/D
* Nach Antwort:

  * ✅/❌ Feedback (kurz)
  * Bei ❌: 1 kurze Erklärung (max. 1 Satz)
  * CTA: „Nächste Frage“

**Nach Frage 5:** Ergebnis-Screen (siehe 6).

---

## 4. Home-Menü (Main Hub)

### 4.1 Minimal Hub (Day 0–1)

**Text:**

* „Was willst du heute spielen?“

**Buttons:**

* ▶️ Spielen
* 🔥 Daily Challenge
* 🎁 Freund einladen
* ℹ️ Hilfe

---

### 4.2 Standard Hub (Unlocked)

Wird freigeschaltet, sobald:

* Spiele gesamt ≥ 3 **oder**
* Streak ≥ 2 Tage

**Buttons zusätzlich:**

* 📊 Statistik
* ⚙️ Einstellungen

---

### 4.3 Advanced Hub (Tournaments)

Wird freigeschaltet, sobald:

* Spiele gesamt ≥ 10 **und**
* Streak ≥ 3 Tage

**Buttons zusätzlich:**

* 🏆 Turniere

Pakete erscheinen erst nach:

* Spiele gesamt ≥ 5 **oder**
* 1 Teilnahme an Challenge

**Buttons zusätzlich:**

* ⭐ Pakete

---

## 5. Spielen (Core Entry)

### 5.1 Spielen — Auswahl (Standard)

**Text:** „Wähle einen Modus:“

**Buttons:**

* ⚡ Quick Mix (A1)
* ⚡ Quick Mix (A2)
* 🧩 Mini-Spiele
* ♾️ Endless Lite

**Hinweis:** Modus-Liste bleibt kurz.

---

### 5.2 Mini-Spiele

**Buttons:**

* der/die/das Sprint
* Wortstellung Blitz
* Trennbare Verben
* Akkusativ/Dativ Mini

---

## 6. Ergebnis-Screen (nach jeder Session) — Viral Default

Nach jeder Session zeigt der Bot IMMER:

**Ergebnis Block:**

* Score: „8/10“
* Streak: „🔥 3 Tage“ (wenn vorhanden)
* Ranking (falls aktiv): „Heute: #37“

**Buttons:**

* 🔁 Nochmal spielen
* 🧑‍🤝‍🧑 Challenge senden
* 📤 Ergebnis teilen

Optional (wenn unlock):

* 📊 Statistik
* 🏆 Turniere

---

## 7. Challenge Flow (Virality Loop)

### 7.1 Challenge erstellen

Aus Ergebnis-Screen:

* „🧑‍🤝‍🧑 Challenge senden“

Bot:

* erstellt Challenge-ID
* generiert Deep-Link
* zeigt Copy-Message:

  * „Schaffst du mehr als ich? 💪“

**Buttons:**

* 📤 Challenge teilen
* ▶️ Challenge spielen (für Sender: Revanche/Trainingsrunde)

---

### 7.2 Challenge annehmen

Wenn Nutzer über Deep-Link kommt:

Bot:

* „Du wurdest herausgefordert!“
* CTA: **„▶️ Challenge starten“**

Nach Abschluss:

* Vergleich: „Du: 6/10 | Valerii: 8/10“ (Name nur wenn vorhanden)

**Buttons:**

* 🔁 Revanche
* 🧑‍🤝‍🧑 Weiterleiten
* 📤 Ergebnis teilen

---

## 8. Daily Challenge (Retention Core)

### 8.1 Daily Entry

**Text:**

* „Heute wartet deine Challenge: 7 Fragen.“

**Buttons:**

* ▶️ Start

Nach Abschluss:

* Ergebnis-Screen + Bonus-Text:

  * „Komm morgen wieder, um deinen Streak zu halten.“

---

## 9. Streak Regeln (User-visible)

* Streak startet nach 1 abgeschlossenem Spiel pro Tag
* Daily Challenge zählt immer
* Nur 1 Spiel pro Tag nötig (keine Überforderung)

**UI:**

* Streak wird im Ergebnis-Screen und in Statistik angezeigt

---

## 10. Statistik (Unlocked)

### 10.1 Inhalt (Minimal)

* Spiele gesamt
* Beste Score-Serie
* Streak
* Stärkste Kategorien
* Schwächste Kategorien

**Buttons:**

* ▶️ Trainiere Schwächen (führt zu Smart Mix / Topic Run sobald verfügbar)

---

## 11. Einstellungen (Unlocked)

* Niveau: A1 / A2 / B1
* Tempo: Normal / Schnell (nur UI pacing)
* Erklärungen: Kurz / Aus (Kurz ist default)

---

## 12. Turniere (Unlocked)

### 12.1 Turnier Lobby

**Buttons:**

* ⚔️ Sit & Go (kurz)
* 🗓️ Daily Turnier
* 🏅 Weekly Main Event
* 👥 Community (gratis)

**Anzeige:**

* Startzeit / Teilnehmer

---

## 13. Pakete (Unlocked)

### 13.1 Paket Screen

**Text:**

* „Mehr Modi. Mehr Training. Mehr Wettbewerb.“

**Buttons:**

* ⭐ Starter
* ⭐ Progress
* ⭐ Pro

**Regel:** Pakete dürfen nie die Basis-Funktionen blockieren.

---

## 14. Hilfe / Datenschutz

**Hilfe:**

* Kurz: „So funktioniert’s“

**Datenschutz:**

* /privacy
* /delete_me

---

## 15. Error UX (Wichtig)

* Immer klare Fehlermeldung
* Immer ein Button „Zurück zum Menü“
* Keine technischen Details im UI

---

## 16. DoD (Definition of Done) — UX Flow

Ein UX Flow ist DONE wenn:

* Day-0 Menü ist minimal und klar
* Erste Frage startet in ≤ 20 Sekunden
* Ergebnis-Screen enthält immer Challenge + Share
* Progressive Unlock Regeln sind implementierbar
* Keine UI ist in einer anderen Sprache als Deutsch

---

## 17. Open Decisions (für spätere Slices)

* Exakte Unlock-Schwellen ggf. A/B testen
* Share Card Design (Text-only vs. Bild)
* Tournament Reward Details (Badges/Access)
