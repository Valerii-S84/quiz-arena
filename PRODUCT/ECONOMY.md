# ECONOMY

## Deutsch ist einfach! — Quiz Arena

**Sprache:** Deutsch (Bot-UI & Dokumentation) — STRICT

---

## 1. Ziel dieses Dokuments

Dieses Dokument definiert die vollständige wirtschaftliche Logik von *Deutsch ist einfach! — Quiz Arena*.

Es regelt:

* Paketstruktur
* Zugangslogik
* Freischaltungsmechanismen
* Streak-Mechanik
* Referral-Belohnungen
* Interne Vorteile

Dieses Dokument garantiert:

* Keine versteckten Paywalls
* Keine Glücksspiel-Elemente
* Nachhaltige Monetarisierung
* Balance zwischen Free und Premium

---

## 2. Grundprinzipien der Economy

1. Basis-Spiel bleibt immer kostenlos.
2. Bezahlt wird für Zugang, Komfort und Status – nicht für Fragen oder Siege.
3. Keine Funktion darf "Pay-to-Win" erzeugen.
4. Monetarisierung darf Retention nicht zerstören.
5. Wettbewerb bleibt fair.

---

## 3. Monetarisierungsmodell

Monetarisierung erfolgt über:

* ⭐ Paketkäufe (Telegram Stars)
* Turnier-Teilnahmen (optional)
* Saisonale Premium-Zugänge

Es gibt **keine**:

* Stars-Auszahlungen
* Handelbare Vorteile
* Echtgeld-Gewinne

---

## 4. Paketstruktur

### 4.1 Starter Paket

Zielgruppe: Neue aktive Nutzer

Enthält:

* Zugang zu Topic Run
* Zugang zu Smart Mix
* 2 Free Turnier-Entries
* Erweiterte Statistik

Charakter: Einstieg in Premium ohne Überforderung

---

### 4.2 Progress Paket

Zielgruppe: Regelmäßige Spieler

Enthält:

* Zugang zu Exam Mode
* Endless Pro
* 1 Streak Freeze pro Woche
* 5 Free Turnier-Entries
* Priority Ranking Anzeige

Charakter: Leistungsorientierte Spieler

---

### 4.3 Pro Paket

Zielgruppe: Power User

Enthält:

* Zugang zu allen Modi
* Teilnahme an Closed Turnieren
* 2 Streak Freezes pro Woche
* Exklusive Badge
* Saisonale Events Zugang

Charakter: Status + Wettbewerb

---

## 5. Freischaltungslogik (Non-Monetary Unlock)

Bestimmte Features werden freigeschaltet durch:

* Anzahl gespielter Spiele
* Streak-Länge
* Turnier-Teilnahme

Beispiele:

* Turniere sichtbar ab 10 gespielten Spielen
* Statistik ab 3 Spielen
* Exam Mode nach 20 Spielen oder Paket

Bezahlung darf Freischaltung beschleunigen, aber nicht exklusiv erzwingen.

---

## 6. Streak Economy

### 6.1 Grundregeln

* 1 abgeschlossenes Spiel pro Tag hält Streak
* Daily Challenge zählt immer

### 6.2 Streak Freeze

* Verhindert Streak-Verlust für 1 Tag
* Limitierte Anzahl pro Woche
* Nicht stapelbar

### 6.3 Streak Repair

Optionaler Mechanismus (zukünftiger Slice):

* Einmalige Wiederherstellung
* Nur mit Paket oder Event

---

## 7. Turnier Entry Economy

### 7.1 Free Entries

* Durch Pakete
* Durch Turnier-Erfolge
* Durch Referral-Milestones

### 7.2 Paid Entries

* Teilnahme gegen Stars
* Kein Einfluss auf Gewinnwahrscheinlichkeit

---

## 8. Referral System

### 8.1 Referral Prinzip

Jeder Nutzer erhält individuellen Link.

### 8.2 Referral Milestones

Aktive Produktlogik (Stand: 26.02.2026):

* Jede **3** qualifizierten Freunde → **1** Belohnungs-Slot
* Cap: **2 Belohnungen pro Monat** pro Referrer
* Delay: Belohnung wird erst **48h nach qualified_at** claimable
* Reward Choice: **MEGA_PACK_15** oder **PREMIUM_STARTER**

Hinweis: Die alten Milestones `1/3/5/10` wurden verworfen, um Fraud-Risiko und Reward-Inflation zu senken und den Claim-Flow klar/idempotent zu halten.

Referral-Belohnungen dürfen keine Stars enthalten.

---

## 9. Interne Vorteile (Non-Transferable)

Mögliche interne Vorteile:

* Extra Entry
* Streak Freeze
* Premium-Zeitfenster
* Exklusive Badge

Diese Vorteile:

* sind nicht handelbar
* nicht übertragbar
* nicht in Stars umwandelbar

---

## 10. Balance-Regeln

Free-Spieler müssen:

* täglich spielen können
* an Community-Turnieren teilnehmen können
* Fortschritt sehen können

Premium-Spieler erhalten:

* mehr Modi
* mehr Komfort
* mehr Wettbewerbschancen

Aber keinen unfairen Vorteil.

---

## 11. Anti-Inflation Regeln

* Free Entries haben Wochenlimit
* Streak Freeze begrenzt
* Premium-Zugänge zeitlich limitiert

Keine unbegrenzten Ressourcen.

---

## 12. Monetarisierungsphilosophie

Ziel ist:

* langfristige Retention
* moderate, faire Konversion
* emotionale Bindung statt Druck

Keine aggressiven Verkaufsnachrichten.

---

## 13. Definition of Done — Economy

Dieses Dokument ist DONE wenn:

* Pakete klar definiert sind
* Unlock-Logik eindeutig ist
* Keine Pay-to-Win Struktur existiert
* Turnier-Teilnahme sauber integriert ist
* Monetarisierung Vision-konform ist

---

## 14. Erweiterungen (spätere Slices)

* Saison-Pass
* Battle Pass Logik
* Elo-basierte Divisions
* Limited-Time Bundles

Nur mit separatem Slice erlaubt.
