# IMPLEMENTATION_ARCHITECTURE.md

> Scope: Production-Grade Architektur für **eine Sprache (Deutsch)**, ein Telegram-Quiz-Produkt mit Game Modes, Tournament Engine, Economy (Pakete via Telegram Stars), Anti-Cheat und sauberer Deployment-Topologie.

## 0. Invarianten (nicht verhandelbar)

* **Kein MVP.** Wir bauen sofort production-grade.
* **Bot-Schicht bleibt dünn.** Keine Business-Logik in `app/bot/*`.
* **Hard Limit: 250 Zeilen pro Datei.** (siehe `CODE_STYLE.md`)
* **Determinismus & Testbarkeit** für Kernregeln (Selection/Ranking/Rewards).
* **UI-Texte nur Deutsch**, zentral in `app/bot/texts/de.py`.

## 1. Tech-Stack

### 1.1 Backend

* **Python 3.12+**
* **FastAPI** (HTTP API für Health, Admin, Webhooks)
* Async Runtime: **uvicorn**
* Dependency Injection: simpel (keine Magic-Frameworks)

### 1.2 Telegram Bot Layer

* Telegram Bot Framework: z. B. **aiogram** (async) oder **python-telegram-bot** (async). Entscheidung: **async-first**.
* Betrieb:

  * **Webhooks** in Production (stabiler, skalierbarer als Long Polling)
  * Optional Long Polling nur lokal/dev

### 1.3 Datenbank

* **PostgreSQL 15+**
* ORM/DB-Zugriff:

  * SQLAlchemy 2.0 (async) oder SQLModel (falls strikt limitiert)
  * Repositories in `app/db/repo/`
* Migrationen: **Alembic** (Pflicht)

### 1.4 Scheduler / Background Jobs

* **Celery + Redis** (robust, etabliert) *oder* **APScheduler** (einfacher, aber weniger robust).
* Production-Grade Empfehlung: **Celery + Redis**

  * Redis als Broker
  * Optional: Redis als distributed lock store

### 1.5 Observability

* Structured Logging (JSON)
* Metrics: Prometheus endpoint (optional ab Tag 1; mindestens vorbereiten)
* Error Tracking: Sentry (optional)

## 2. Architektur-Topologie

### 2.1 Komponenten

1. **Telegram Bot Service**

* nimmt Updates an (Webhook)
* validiert Input
* ruft Domain-Use-Cases auf
* rendert Antworten/Keyboards

2. **API Service (FastAPI)**

* Health/Readiness
* Admin endpoints (z. B. Turniere starten/stoppen, Feature Flags)
* ggf. Payment Webhook / Telegram Payment confirmation flows

3. **Worker Service (Celery)**

* Tournament Scheduler
* Reward distribution
* Cleanup jobs
* Anti-abuse Batch checks

4. **PostgreSQL**

* Source of truth

5. **Redis**

* Celery broker
* Locks/Rate limit (optional)

### 2.2 Kommunikation

* Bot → Domain: in-process calls
* Worker → Domain: in-process calls
* Domain → DB: Repos
* Domain → Telegram: **nie direkt** (nur Bot-Schicht)

## 3. Domain Boundaries

### 3.1 Module

* `app/game/*`: Game Modes, question selection, scoring primitives
* `app/tournaments/*`: lifecycle, ranking, rewards
* `app/economy/*`: packages, entitlements, purchases
* `app/services/*`: scheduler, payments, analytics (infra)
* `app/db/*`: models, migrations, repos
* `app/bot/*`: handlers, keyboards, texts

### 3.2 Regel: Keine Zyklus-Imports

* `bot` darf `game/tournaments/economy/services` importieren
* Domains dürfen `bot` nie importieren

## 4. Datenmodell (High-Level)

> Konkretes Schema existiert bereits als Data Schema; hier nur die Implementation-Constraints.

### 4.1 Kern-Entitäten (implizit)

* User
* Session (laufendes Spiel / Zustand)
* Question (+ options)
* AnswerEvent (user answered)
* Tournament (+ state)
* TournamentParticipation
* RankingSnapshot (optional)
* EconomyPackage
* Purchase
* Entitlement (was der User „hat“)
* RewardTransaction (idempotent)

### 4.2 ACID & Idempotenz

* Rewards/Purchases müssen **idempotent** sein:

  * eindeutige `idempotency_key`
  * unique constraints in DB
* Race conditions verhindern:

  * `SELECT ... FOR UPDATE` in kritischen Transaktionen
  * oder distributed locks (Redis) + DB constraints

## 5. Concurrency & Consistency

### 5.1 Grundprinzip

* DB ist Source-of-Truth.
* **DB Constraints** sind die letzte Schutzschicht.

### 5.2 Locking-Strategie

* Tournament Lifecycle Änderungen (Start/End/Reward) werden serialisiert:

  * Option A (bevorzugt): DB Transaction + row lock auf Tournament
  * Option B: Redis lock `tournament:{id}` + DB transaction

### 5.3 Outbox Pattern (optional, production-grade)

* Für Events (Reward issued, Purchase confirmed):

  * insert event in `outbox` innerhalb der gleichen Transaktion
  * worker verarbeitet outbox, markiert processed
* Vorteil: robust bei Crash/Retry.

## 6. Tournament Engine Implementation

### 6.1 Lifecycle States

* `DRAFT` → `SCHEDULED` → `ACTIVE` → `FINISHED` → `REWARDED`
* Zustandswechsel sind nur über Use-Cases erlaubt.

### 6.2 Scheduler Jobs

* `start_tournament(tournament_id)`
* `finish_tournament(tournament_id)`
* `issue_rewards(tournament_id)`

Jeder Job:

* ist idempotent
* prüft aktuellen State
* führt State Transition in DB Transaction aus

### 6.3 Ranking

* Ranking basiert auf AnswerEvents:

  * deterministisches Scoring
  * Ties: definierte Tie-Break Regeln (z. B. earliest completion)
* Option für Performance:

  * Snapshotting (periodische RankingSnapshot)
  * Materialized views (später)

## 7. Question Selection Engine (Anti-Repeat)

### 7.1 Ziele

* Keine „billigen“ Wiederholungen
* Abstand zwischen gleichen Correct Answers / Mustern
* deterministisch testbar

### 7.2 Mechanik (Production Rule Set)

* Pro User wird ein History-Fenster gepflegt (z. B. last N questions/events)
* Selection constraint:

  * gleiche `question_id` nicht innerhalb von N
  * gleiche `correct_option_id` nicht innerhalb von M
  * gleiche `pattern_key` (falls vorhanden) nicht innerhalb von K
* Fallback:

  * wenn Constraints zu strikt, relax in definierter Reihenfolge (und loggen)

### 7.3 Determinismus

* Zufall nur über kontrollierten RNG:

  * Seed = `hash(user_id + session_id + date_bucket)`
* Unit Tests setzen Seed fix.

## 8. Economy (Telegram Stars Pakete)

### 8.1 Produktmodell

* Wir verkaufen **Pakete** (z. B. „10 Spiele“, „Premium Turnier Eintritt“, „Extra Leben“ etc.)
* Kauf wird bezahlt über **Telegram Stars**.

### 8.2 Flow (high-level)

1. User wählt Paket im Bot
2. Bot initiiert Payment (Telegram)
3. Nach erfolgreichem Payment:

   * `Purchase` wird erstellt (idempotent)
   * `Entitlement` wird vergeben
   * `RewardTransaction`/`Ledger` wird geschrieben

### 8.3 Sicherheitsregeln

* Jede Payment-Confirmation wird serverseitig validiert.
* Double-spend verhindert durch:

  * unique constraint auf Telegram payment identifier
  * idempotency_key
* Entitlements haben klare Gültigkeit (z. B. Anzahl Uses / expiry)

## 9. Anti-Cheat / Anti-Abuse

### 9.1 Ziele

* Bot-Spam / Macro / Multi-Account Patterns reduzieren
* Score-Manipulation erschweren

### 9.2 Maßnahmen (Tag 1)

* Rate limiting pro User/Chat (Redis token bucket optional)
* Session integrity:

  * Antworten nur, wenn Session ACTIVE
  * Zeitfenster pro Frage
  * reject duplicate answer events (unique constraint)
* Tournament:

  * nur gültige AnswerEvents zählen
  * suspicious patterns flaggen (später)

### 9.3 Measures (später, aber schon architekturfähig)

* Device fingerprinting ist in Telegram limitiert → Fokus auf Behavior
* anomaly scoring via analytics pipeline

## 10. API Surface (Minimal, aber production)

### 10.1 Internal Admin Endpoints (auth required)

* `POST /admin/tournaments/{id}/schedule`
* `POST /admin/tournaments/{id}/start`
* `POST /admin/tournaments/{id}/finish`
* `POST /admin/tournaments/{id}/rewards/issue`
* `GET /health`
* `GET /ready`

### 10.2 Security

* Admin via:

  * Basic allowlist (IP) + token
  * oder OAuth später

## 11. Deployment

### 11.1 Ziel-Topologie (VPS/Cloud)

* 1× VM (Start) mit Docker Compose:

  * `bot` (Webhook)
  * `api` (FastAPI)
  * `worker` (Celery)
  * `postgres`
  * `redis`
  * `nginx`/`caddy` (TLS termination)

### 11.2 Webhooks

* TLS zwingend (LetsEncrypt)
* Secret path oder signature verification

### 11.3 Backups

* Postgres daily backup + retention
* Restore getestet (runbook)

## 12. Scaling Considerations (ohne Multi-Language, aber future-safe)

> Wir optimieren **jetzt** für DE-only, aber ohne Sackgassen.

* Bot/API horizontal skalierbar (stateless)
* DB skaliert vertikal + Indizes
* Worker skaliert über concurrency
* Hot paths:

  * selection queries
  * ranking aggregation

### 12.1 Indizes (typisch)

* AnswerEvent: `(user_id, created_at)`
* Participation: `(tournament_id, user_id)`
* Purchase: unique on `(provider_payment_id)`

## 13. Test Strategy

* Unit Tests: alle Kernalgorithmen (Selection, Ranking, Rewards, Entitlements)
* Integration Tests:

  * DB repos (Testcontainers optional)
  * Tournament jobs end-to-end
* Contract Tests:

  * Bot handler → Use-case interfaces

## 14. Failure & Recovery

* Worker Jobs sind retry-safe (idempotent)
* DB Constraints verhindern doppelte Rewards/Purchases
* Outbox (optional) erhöht Robustheit
* Runbooks:

  * „Webhook down“
  * „DB restore“
  * „Worker backlog“

## 15. Konkrete Use-Case Interfaces (canonical)

> Diese Use-Cases sind die „öffentlichen“ Eintrittspunkte der Domain.

### Game

* `start_session(user_id, mode) -> session`
* `get_next_question(session_id) -> question`
* `submit_answer(session_id, question_id, option_id) -> result`

### Tournaments

* `schedule_tournament(spec) -> tournament_id`
* `start_tournament(tournament_id)`
* `finish_tournament(tournament_id)`
* `compute_ranking(tournament_id) -> ranking`
* `issue_rewards(tournament_id)`

### Economy

* `list_packages() -> packages`
* `init_purchase(user_id, package_id) -> payment_payload`
* `confirm_purchase(provider_event) -> purchase_result`
* `grant_entitlement(user_id, entitlement_spec)`

---

# Done Criteria (SLICE_06)

* Dieses Dokument ist die einzige Quelle der Wahrheit für Implementation-Topologie.
* Keine Widersprüche zu: Vision, UX Flow, Game Modes, Tournament Engine, Economy, Data Schema, Engineering Rules.
* Alle kritischen Risiken sind adressiert: Race Conditions, Idempotenz, Anti-Repeat, Double Rewards, Payment Safety.
