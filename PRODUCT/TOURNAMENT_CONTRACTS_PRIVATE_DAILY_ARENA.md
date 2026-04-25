# TOURNAMENT CONTRACTS — PRIVATE + DAILY_ARENA

## 1. Purpose

This document fixes the runtime source-of-truth for the two active tournament
types in this repository:

* `PRIVATE`
* `DAILY_ARENA`

It exists because the generic `PRODUCT/TOURNAMENT_ENGINE.md` is broader than the
current runtime and still contains rules for tournament types that are not part
of the active implementation. Where this document defines a more specific rule
for `PRIVATE` or `DAILY_ARENA`, this document wins.

## 2. Authoritative Inputs

The contracts below are derived from the current repository sources that already
act as user-facing or runtime-facing truth:

* `app/bot/texts/de.py`
* `app/bot/keyboards/tournament.py`
* `app/bot/keyboards/daily_cup.py`
* `app/game/tournaments/constants.py`
* `app/game/tournaments/queries.py`
* `app/game/tournaments/start.py`
* `app/game/tournaments/daily_cup_standings.py`
* `app/workers/tasks/daily_cup_config.py`
* `app/workers/tasks/daily_cup_proof_cards_context.py`
* `app/workers/tasks/tournaments_messaging.py`
* `app/workers/tasks/tournaments_proof_cards_delivery.py`
* `tests/integration/test_daily_arena_golden_integration.py`
* `tests/integration/test_daily_cup_worker_integration.py`
* `tests/integration/test_daily_cup_standings_integration.py`
* `tests/bot/test_daily_cup_flow.py`
* `PRODUCT/TOURNAMENT_ENGINE.md`

## 3. Baseline Contracts

### 3.1 PRIVATE Tournament

`PRIVATE` is a creator-owned Swiss tournament with these fixed player-visible
rules:

* creator invites up to 7 other players
* total capacity is 8 players
* the creator starts the tournament manually
* minimum participants to start is 2
* the tournament runs for 3 rounds
* the tournament format is chosen at creation time (`5` or `12` questions)

### 3.2 DAILY_ARENA

`DAILY_ARENA` is the active daily cup mode with these fixed player-visible
rules:

* one cup per day
* registration opens before the daily start window and closes before round 1
* all participants play every round
* no elimination
* rounds total is `3` for smaller fields and `4` for larger fields
* each match has `7` questions
* win = `2` points
* draw = `1` point
* rewards are unlocked only from `13` participants

## 4. Ratified Contracts and Current Runtime Gaps

Section 4 distinguishes between the current runtime behavior that exists today
and the ratified contract that future fixes must converge to. Where the current
runtime diverges, the divergence is stated explicitly.

### 4.1 PRIVATE Registration Deadline

Current runtime:

* join is valid only while `status == REGISTRATION` and `now < registration_deadline`
* manual start currently requires creator ownership, `status == REGISTRATION`,
  and enough participants, but it does not check `registration_deadline`
* a `PRIVATE` tournament may therefore remain startable after
  `registration_deadline` until another lifecycle path changes its state

Ratified contract:

* `registration_deadline` is the hard end of the registration window
* after the deadline, the tournament must be non-joinable and non-startable
* the contract does not allow a post-deadline manual start

### 4.2 DAILY_ARENA Round Deadline

Current runtime gap:

* the round-deadline path currently allows a per-match action to tighten both
  `tournament_match.deadline` and the shared `tournament.round_deadline`

Ratified contract:

* `tournament.round_deadline` is the shared deadline for the active tournament
  round and must be identical for every participant in that round
* round messages, lobby views, reminders, and worker transitions must all use
  the same round-level deadline
* per-match adjustments may change `tournament_match.deadline`
* per-match adjustments must never mutate the shared
  `tournament.round_deadline`

### 4.3 DAILY_ARENA Minimum Participants

Current runtime:

* `settings.daily_cup_min_participants` is exposed through
  `DAILY_CUP_MIN_PARTICIPANTS`
* the registration close cancel/start branch still uses the hardcoded
  `TOURNAMENT_MIN_PARTICIPANTS = 4`
* the runtime therefore does not yet have one minimum-participants source of
  truth

Ratified contract:

* registration close
* cancel/start branching
* any user-visible or worker-visible minimum-participant checks

must all resolve from the same configured value, not from duplicated hardcoded
constants.

### 4.4 Tournament Ranking

Current runtime:

* `DAILY_ARENA` standings are deterministic and already end with `user_id asc`
* `PRIVATE` standings currently sort by `score desc`, `tie_break desc`,
  `joined_at asc` and do not yet apply a final `user_id asc` fallback

Ratified contract:

* tournament ranking must always be deterministic
* no final order may depend on database return order
* `PRIVATE`: `score desc`, `tie_break desc`, `joined_at asc`, `user_id asc`
* `DAILY_ARENA`: `wins desc`, `correct_answers desc`, `total_time_ms asc`,
  `joined_at asc`, `user_id asc`

The final `user_id asc` fallback is required to keep the ordering stable under
full equality.

### 4.5 Daily Cup Share Semantics

Current runtime gap:

* the repeat-share handler path looks for a `button.url` share action, while
  the active keyboard uses `switch_inline_query`
* the `msg.daily_cup.share.thanks` branch is therefore unreachable in the
  current implementation

Ratified contract:

* first share tap on a completed result creates the share UI and enqueues the
  user proof card
* repeat share tap from a message that already contains the share action must
  answer with `msg.daily_cup.share.thanks`
* the repeat path is an acknowledgement path, not a proof-card requeue path

### 4.6 Proof Card Eligibility Acknowledgements

Current runtime gap:

* stale completed messages for old daily cups may still answer
  `msg.daily_cup.proof_card.queued` even when the worker will intentionally
  skip delivery for that tournament

Ratified contract:

* user-visible proof-card acknowledgements must be truthful
* `msg.daily_cup.proof_card.queued` is allowed only if a proof-card job is
  actually eligible to run
* stale completed messages for old daily cups must not acknowledge a proof card
  as queued if the worker will intentionally skip that tournament

### 4.7 Proof Card Delivery Idempotence

Current runtime:

* `DAILY_ARENA` uses `proof_card_sent` as an explicit delivery guard
* `PRIVATE` caches `proof_card_file_id` for resend reuse but does not yet have
  a separate participant-level sent guard

Ratified contract:

* proof-card delivery is an idempotent participant-level operation for both
  active tournament types
* automatic completion follow-ups must send at most one canonical proof-card
  delivery per participant
* repeated user-triggered requests may resend the already prepared card
* repeated requests must reuse cached file ids when available
* repeated requests must not create duplicate side effects such as duplicate
  rewards or duplicate canonical-delivery state transitions

### 4.8 Share URL Semantics

Current runtime:

* interactive tournament share builders use the public Telegram share contract
  with `https://t.me/share/url`, `url=...`, and `text=...` when share text is
  part of the UX contract
* the private worker-generated standings share button currently emits a
  different URL pattern that omits the `text=...` part

Ratified contract:

* tournament share links use the same public Telegram share contract
  `https://t.me/share/url`
* `url=...`
* `text=...` when share text is part of the UX contract
* worker-generated tournament share buttons must follow the same URL pattern as
  the interactive tournament builders

## 5. Delivery Rules for Future Fixes

Any code change for `PRIVATE` or `DAILY_ARENA` must preserve the ratified
contracts in section 4 unless this document is explicitly updated in the same
change.

Any test added for the audited defects from `2026-04-25` must map directly to
one or more ratified contracts in section 4.
