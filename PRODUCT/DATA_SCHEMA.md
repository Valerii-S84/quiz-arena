# DATA SCHEMA

## Deutsch ist einfach! — Quiz Arena

**Sprache:** Deutsch (Dokumentation) — STRICT

---

## 1. Ziel dieses Dokuments

Dieses Dokument definiert das Datenmodell (Schema) für:

* Nutzerprofile
* Spiele/Session-Tracking
* Fragenbank-Index
* Challenge-System
* Turnier-System
* Economy (Pakete, Zugänge)
* Referral-Tracking
* Datenschutzfunktionen

Das Schema ist minimal, aber vollständig.

---

## 2. Grundsätze

1. Datenminimierung: nur speichern, was für Funktionalität nötig ist.
2. Keine sensiblen Daten (Telefon, Adresse etc.).
3. Vollständige Löschung via `/delete_me`.
4. Auditierbarkeit: zentrale Events und Zustände nachvollziehbar.

---

## 3. Entities (Tabellen)

### 3.1 users

**Zweck:** Nutzerkonto und globale Einstellungen

Felder:

* user_id (PK, Telegram ID)
* username (nullable)
* created_at
* last_active_at
* ui_level (enum: A1, A2, B1)
* explanations_mode (enum: short, off)
* pace_mode (enum: normal, fast)
* is_banned (bool)
* ban_reason (nullable)

---

### 3.2 user_stats

**Zweck:** Aggregierte Nutzerstatistik

Felder:

* user_id (PK/FK)
* games_total
* correct_total
* wrong_total
* best_streak
* current_streak
* last_streak_date (date)
* daily_challenge_last_played (date)
* endless_lite_last_played (date)

---

### 3.3 content_files

**Zweck:** Index der Excel/Quellen-Dateien

Felder:

* file_id (PK)
* file_name
* topic (string)
* quiz_type (string)
* level (enum: A1, A2, B1)
* status (enum: active, test, archived)
* weight (int)

---

### 3.4 questions

**Zweck:** Normalisierte Fragen (importiert aus Excel)

Felder:

* question_id (PK) (string, stabil)
* file_id (FK)
* topic
* quiz_type
* level
* question_text
* option_1
* option_2
* option_3
* option_4
* correct_option_id (int 1–4)
* correct_answer
* explanation (string)
* key (string)
* status (enum: active, disabled)

Hinweis:

* `topic/quiz_type/level` werden redundant gespeichert zur schnellen Filterung.

---

### 3.5 user_question_history

**Zweck:** Anti-Repeat & Cooldown pro Nutzer

Felder:

* user_id (FK)
* question_id (FK)
* last_seen_at (timestamp)
* times_seen (int)

PK:

* (user_id, question_id)

---

### 3.6 sessions

**Zweck:** Jede Spielsession (nicht Turnier)

Felder:

* session_id (PK)
* user_id (FK)
* mode (enum: quick_mix_a1, quick_mix_a2, mini_artikel, mini_word_order, mini_trennbar, mini_cases, endless_lite, topic_run, smart_mix, exam_mode, endless_pro, daily_challenge)
* started_at
* finished_at (nullable)
* total_questions
* correct
* wrong
* total_time_ms
* seed (nullable)
* source (enum: menu, challenge, referral, tournament_reward)

---

### 3.7 session_questions

**Zweck:** Welche Fragen in welcher Session gespielt wurden

Felder:

* session_id (FK)
* order_index (int)
* question_id (FK)
* chosen_option_id (int nullable)
* is_correct (bool nullable)
* answered_at (timestamp nullable)
* time_ms (int nullable)

PK:

* (session_id, order_index)

---

### 3.8 challenges

**Zweck:** Challenge-Objekt (Deep-Link)

Felder:

* challenge_id (PK)
* created_by_user_id (FK)
* created_at
* expires_at
* mode (enum: quick_mix_a1, quick_mix_a2, mini_*, smart_mix, topic_run)
* seed
* total_questions
* status (enum: active, expired, closed)

---

### 3.9 challenge_questions

**Zweck:** Fixierte Fragenliste für eine Challenge

Felder:

* challenge_id (FK)
* order_index (int)
* question_id (FK)

PK:

* (challenge_id, order_index)

---

### 3.10 challenge_attempts

**Zweck:** Ergebnisse der Challenge pro Nutzer

Felder:

* challenge_id (FK)
* user_id (FK)
* started_at
* finished_at
* correct
* wrong
* total_time_ms

PK:

* (challenge_id, user_id)

---

### 3.11 tournaments

**Zweck:** Turnier-Definition und Lifecycle

Felder:

* tournament_id (PK)
* type (enum: sitngo, daily, weekly, monthly, community)
* title (string)
* created_at
* starts_at
* ends_at
* min_players (int nullable)
* max_players (int nullable)
* total_questions
* time_per_question_sec
* seed
* status (enum: announced, registration, running, closed, cancelled)

---

### 3.12 tournament_questions

**Zweck:** Fixierte Fragenliste pro Turnier

Felder:

* tournament_id (FK)
* order_index (int)
* question_id (FK)

PK:

* (tournament_id, order_index)

---

### 3.13 tournament_entries

**Zweck:** Teilnahme/Registrierung

Felder:

* tournament_id (FK)
* user_id (FK)
* entered_at
* entry_source (enum: free_entry, stars_paid, reward)
* status (enum: registered, playing, finished, forfeited)

PK:

* (tournament_id, user_id)

---

### 3.14 tournament_results

**Zweck:** Finale Ergebnisse je Teilnehmer

Felder:

* tournament_id (FK)
* user_id (FK)
* correct
* wrong
* total_time_ms
* rank (int)

PK:

* (tournament_id, user_id)

---

### 3.15 packages

**Zweck:** Definiert kaufbare Pakete

Felder:

* package_id (PK) (enum: starter, progress, pro)
* title
* description
* status (enum: active, disabled)

---

### 3.16 user_entitlements

**Zweck:** Zugänge und Vorteile pro Nutzer

Felder:

* user_id (FK)
* entitlement_type (enum: mode_access, premium_until, free_entries, streak_freeze_count, closed_tournaments_access)
* value_int (nullable)
* value_str (nullable)
* valid_until (nullable)
* updated_at

PK:

* (user_id, entitlement_type)

---

### 3.17 purchases

**Zweck:** Kaufhistorie (Stars)

Felder:

* purchase_id (PK)
* user_id (FK)
* created_at
* provider (enum: telegram_stars)
* item_type (enum: package, entry)
* item_id (string)
* stars_amount (int)
* status (enum: pending, paid, failed, refunded)
* telegram_charge_id (nullable)

---

### 3.18 referrals

**Zweck:** Referral-Tracking

Felder:

* ref_id (PK)
* owner_user_id (FK)
* created_at
* code (string unique)

---

### 3.19 referral_events

**Zweck:** Referral-Erfolge (Milestones)

Felder:

* ref_owner_user_id (FK)
* invited_user_id (FK)
* invited_at
* first_game_at (nullable)
* status (enum: clicked, started, activated)

PK:

* (ref_owner_user_id, invited_user_id)

---

### 3.20 events (optional, empfohlen)

**Zweck:** Zentrales Event-Log zur Analyse

Felder:

* event_id (PK)
* user_id (nullable)
* created_at
* event_type (string)
* payload_json (json)

---

## 4. Datenschutz-Operationen

### 4.1 /privacy

* Liefert eine kurze Erklärung, welche Daten gespeichert werden.

### 4.2 /delete_me

* Löscht:

  * users
  * user_stats
  * user_question_history
  * sessions, session_questions
  * challenges_attempts
  * tournament_entries, tournament_results
  * purchases
  * referrals / referral_events (wo relevant)

---

## 5. Konsistenzregeln (Constraints)

* `questions.correct_option_id` muss 1–4 sein.
* Jede Session/Tournament muss eine fixierte Fragenliste besitzen.
* Ranking basiert nur auf `correct`, `wrong`, `total_time_ms`.
* Keine Entitlement darf Stars repräsentieren.

---

## 6. Definition of Done — Data Schema

Dieses Dokument ist DONE wenn:

* Alle Kernfunktionen (UX, Modes, Tournaments, Economy) abgedeckt sind
* Anti-Repeat und Seed-Determinismus technisch möglich sind
* Developer ohne Nachfragen implementieren kann
* Datenschutzoperationen definiert sind
