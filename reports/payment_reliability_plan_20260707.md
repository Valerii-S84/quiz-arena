# Payment Reliability Plan - Telegram Stars / Premium Purchases

Date: 2026-07-07
Local branch inspected: `feature/arena-monetization-pr`
Local SHA inspected: `7c0590a93c56849fae680b14508ec6531cc30f3f`
Production SHA reported in incident: `1fb8a09`
Production path requested for read-only check: `/opt/quiz-arena`

## 1. Incident summary

User `270` paid for `PREMIUM_WEEK` through Telegram Stars.

Known incident facts from task context:

- Telegram Stars transaction existed: `29` Stars at `2026-07-02 11:35:06 UTC`.
- Purchase `92c3c3c5-9ae1-4855-9e6e-141d85f65703` remained in `PRECHECKOUT_OK`.
- DB had no `paid_at`, `credited_at`, `telegram_payment_charge_id`, or `raw_successful_payment`.
- Premium entitlement was not created.
- Customer was manually compensated with `PREMIUM_MONTH`.

Read-only production checkout status:

- `/opt/quiz-arena` is not available in this environment, so the production tree at SHA `1fb8a09` could not be inspected.
- All code facts below are from local branch `feature/arena-monetization-pr` at `7c0590a`.

Reliability goal:

```text
Telegram payment accepted by Telegram
-> bot stores durable payment evidence
-> purchase becomes PAID_UNCREDITED
-> same idempotent crediting path grants entitlement/assets/ledger
-> purchase becomes CREDITED
-> reconciliation and recovery close any gap
-> ambiguous cases alert admins instead of silently losing the customer
```

Telegram API facts used:

- `SuccessfulPayment` is carried on a `Message` object and includes `currency`, `total_amount`, `invoice_payload`, `telegram_payment_charge_id`, and `provider_payment_charge_id`.
- `PreCheckoutQuery` is a separate update type and includes `currency`, `total_amount`, and `invoice_payload`.
- `getStarTransactions` returns the bot's Telegram Star transactions in chronological order and `StarTransaction.id` coincides with `SuccessfulPayment.telegram_payment_charge_id` for successful incoming payments.
- `refundStarPayment` requires `user_id` and `telegram_payment_charge_id`.

Official source: https://core.telegram.org/bots/api

## 2. Current payment flow diagram

```text
User taps buy callback
  -> app/bot/handlers/payments.py:handle_buy
  -> payments_buy_flow.handle_buy_callback
  -> payments_buy.init_buy_purchase
  -> PurchaseService.init_purchase
  -> purchases row CREATED with invoice_payload/idempotency_key
  -> bot.send_invoice(currency="XTR", payload=invoice_payload)
  -> PurchaseService.mark_invoice_sent
  -> purchases.status = INVOICE_SENT

Telegram pre_checkout_query
  -> /webhook/telegram
  -> Celery task process_telegram_update
  -> dispatcher.feed_update
  -> payments.py:handle_precheckout
  -> PurchaseService.validate_precheckout
  -> validate user_id, amount, status, promo reserve
  -> purchases.status = PRECHECKOUT_OK
  -> pre_checkout_query.answer(ok=True)

Telegram message.successful_payment
  -> /webhook/telegram
  -> Celery task process_telegram_update
  -> dispatcher.feed_update
  -> payments.py:handle_successful_payment
  -> payments_runtime.apply_successful_payment
  -> PurchaseService.apply_successful_payment
  -> lock purchase by invoice_payload
  -> validate user, status, XTR, amount
  -> set telegram_payment_charge_id/raw_successful_payment/status=PAID_UNCREDITED/paid_at
  -> credit_purchase_assets
      -> premium: _apply_premium_entitlement
      -> energy/streak/tickets/promo as applicable
      -> ledger_entries PURCHASE_CREDIT for stars_amount > 0
  -> purchases.status = CREDITED, credited_at set
  -> bot sends success text
```

Current webhook/update flow:

```text
POST /webhook/telegram
  -> validate X-Telegram-Bot-Api-Secret-Token
  -> parse JSON
  -> require update_id
  -> enqueue process_telegram_update to Celery
  -> if enqueue fails or times out: 503 {"status":"retry"}
  -> if enqueue succeeds: 200 {"status":"queued"}

Celery process_telegram_update
  -> acquire/update processed_updates(update_id)
  -> Update.model_validate(raw_payload)
  -> dispatcher.feed_update(bot, update)
  -> PROCESSED on success
  -> FAILED + Celery retry on unexpected exception
```

## 3. Current code map

### Webhook / update ingestion

- `app/main.py`
  - `create_app()` includes `telegram_webhook_router`.
- `app/api/routes/telegram_webhook.py`
  - `telegram_webhook()` handles `POST /webhook/telegram`.
  - `_enqueue_update()` enqueues `process_telegram_update`.
  - If enqueue fails, the endpoint returns `503` so Telegram can retry.
  - It does not persist raw update payload in DB before ACK.
- `app/services/telegram_updates.py`
  - `extract_update_id()`.
  - `is_valid_webhook_secret()`.
- `app/workers/tasks/telegram_updates.py`
  - `process_telegram_update` Celery task with `acks_late=True`, `reject_on_worker_lost=True`.
  - Retries on unexpected exceptions.
- `app/workers/tasks/telegram_updates_processing.py`
  - `process_update_async()`.
  - Uses `processed_updates` as update-level idempotency status.
  - Calls `dispatcher.feed_update(bot, update)`.
- `app/db/models/processed_updates.py`
  - Stores `update_id`, `processed_at`, `status`, `processing_task_id`.
  - Does not store raw update payload or payment metadata.
- `app/bot/application.py`
  - `build_dispatcher()` includes `payments_router`.
  - No inspected global middleware blocks service messages; `FsmCleanupMiddleware` only clears state for `/start` or selected callbacks.

### Webhook registration / allowed updates

- `docs/runbooks/telegram_sandbox_stars_smoke.md`
  - Calls `setWebhook` with URL and `secret_token`.
  - Does not set or assert `allowed_updates`.
- `docs/runbooks/first_deploy_and_rollback.md`
  - Calls `setWebhook` without `allowed_updates`.
- `docs/operations/production_state_checks.md`
  - Checks webhook URL, `pending_update_count`, and `last_error_*`.
  - Does not currently require `allowed_updates` to include `message` and `pre_checkout_query`.
- `docs/infra/production_infrastructure_separation_runbook.md`
  - Reads `allowed_updates` in one status snippet, but the payment smoke runbook does not enforce the payment-specific list.

### Payment handlers

- `app/bot/handlers/payments.py`
  - `handle_precheckout()` catches expected validation errors and answers `ok=False`.
  - `handle_precheckout()` answers `ok=True` after `PurchaseService.validate_precheckout`.
  - `handle_successful_payment()` handles `@router.message(F.successful_payment)`.
  - `handle_successful_payment()` catches expected purchase/product/precheckout errors and answers failure text.
  - It does not emit dedicated structured before/after crediting logs for payment crediting.
  - It does not send a payment-specific ops alert on unexpected exceptions.
- `app/bot/handlers/payments_runtime.py`
  - `validate_precheckout()` maps Telegram user to internal user, then calls `PurchaseService.validate_precheckout`.
  - `apply_successful_payment()` passes `invoice_payload`, `telegram_payment_charge_id`, and `payment.model_dump(exclude_none=True)` into `PurchaseService.apply_successful_payment`.
  - It does not pass or persist `update_id`; this makes update-level audit harder.
- `app/bot/handlers/payments_buy_completion.py`
  - `send_purchase_invoice()` sends Stars invoice with `currency="XTR"` and `payload=init_result.invoice_payload`.
  - `send_purchase_invoice_and_mark_sent()` marks invoice sent only after `send_invoice` succeeds.

### Purchase service / DB invariants

- `app/economy/purchases/service/precheckout.py`
  - `validate_precheckout()` validates purchase by `invoice_payload`, internal `user_id`, `stars_amount`, and current status.
  - Precheckout does not credit product, which is correct.
- `app/economy/purchases/service/credit.py`
  - `apply_successful_payment()` locks purchase by `invoice_payload`.
  - It rejects wrong internal user and wrong status.
  - It treats already `CREDITED` purchase as idempotent replay.
  - It validates `currency == "XTR"` for paid purchases.
  - It validates `total_amount` only if present; missing `total_amount` currently passes validation.
  - It writes `telegram_payment_charge_id`, `raw_successful_payment`, `paid_at`, and `status="PAID_UNCREDITED"`, then immediately calls `credit_purchase_assets()`.
  - Current handler transaction means `PAID_UNCREDITED` is normally committed only if crediting reaches `CREDITED`; it is not a durable mid-point for crash-before-credit.
- `app/economy/purchases/service/credit_assets.py`
  - Applies premium entitlement, energy, streak saver, promo usage, ledger, then sets `CREDITED`.
  - Ledger idempotency key is `credit:purchase:{purchase.id}`.
  - It does not check for existing ledger/entitlement before creating; current safety relies on the purchase status replay guard and DB unique keys.
- `app/economy/purchases/service/entitlements.py`
  - `_apply_premium_entitlement()` creates `entitlement:premium:{purchase.id}`.
  - Active premium upgrade revokes old active entitlement and creates a new one.
  - It is not fully idempotent if re-entered after an entitlement from the same purchase was already committed but purchase status did not reach `CREDITED`.
- `app/db/models/purchases.py`
  - Unique: `idempotency_key`, `invoice_payload`, `telegram_payment_charge_id`, `telegram_pre_checkout_query_id`.
  - Partial unique: one active invoice per user/product for statuses `CREATED`, `INVOICE_SENT`, `PRECHECKOUT_OK`.
  - Index: `idx_purchases_paid_uncredited_paid_at`.
- `app/db/models/entitlements.py`
  - Unique: `idempotency_key`.
  - Partial unique: one active premium row per user.
  - Index exists on `source_purchase_id`, but no explicit unique index for premium `source_purchase_id`.
- `app/db/models/ledger_entries.py`
  - Unique: `idempotency_key`.
  - Append-only guard at ORM level; DB trigger added in migration `c9d8e7f6a5b4_m24_ledger_append_only_and_purchase_asset.py`.

### Recovery / reconciliation / alerts

- `app/workers/tasks/payments_reliability_async.py`
  - `recover_paid_uncredited_async()` scans stale `PAID_UNCREDITED` purchases.
  - `_recover_single_purchase()` requires `telegram_payment_charge_id` and dict `raw_successful_payment`; otherwise marks `FAILED_CREDIT_PENDING_REVIEW`.
  - It retries `PurchaseService.apply_successful_payment()` and alerts on review/errors.
  - Default task stale threshold is `2` minutes, not 60 seconds.
- `app/workers/tasks/payments_reliability_reconciliation.py`
  - `run_payments_reconciliation_async()` compares internal DB paid purchases vs ledger credits.
  - It does not call Telegram `getStarTransactions`.
  - It cannot detect "Telegram paid, DB still PRECHECKOUT_OK and paid_at is null" unless another signal exists.
- `app/workers/tasks/payments_reliability_schedule.py`
  - Recovery every 5 minutes.
  - Internal reconciliation every 15 minutes plus daily 03:30 Berlin.
- `app/services/alerts.py`
  - Existing ops alert delivery.
- `docs/analytics/events_catalog.md`
  - Existing ops alert events include `payments_recovery_review_required` and `payments_reconciliation_diff_detected`.

### Existing tests relevant to payment reliability

- `tests/api/test_telegram_webhook.py`
  - Valid secret enqueues update.
  - Enqueue failure returns `503`.
  - Invalid/missing payload is ignored.
- `tests/bot/test_payments_handler_flow.py`
  - Precheckout success/failure.
  - Successful payment success/failure UX.
- `tests/economy/test_purchase_credit_service.py`
  - Wrong user/status, non-XTR, mismatched amount, missing payment payload.
- `tests/integration/test_payments_idempotency_purchase_flow_integration.py`
  - Duplicate successful payment callback credits only once.
- `tests/integration/test_purchase_premium_integration.py`
  - Premium month creates entitlement.
  - Premium upgrade extends/revokes correctly.
- `tests/integration/test_payments_idempotency_recovery_integration.py`
  - Synthetic stale `PAID_UNCREDITED` purchase can be recovered.
- `tests/integration/test_payments_idempotency_reconciliation_integration.py`
  - Internal paid-vs-ledger diff is detected.
- `tests/economy/test_purchase_refund_state_units.py` and `tests/integration/test_purchase_refund_integration.py`
  - Refund idempotency and premium entitlement revoke.

## 4. Exact weak points

1. `successful_payment` depends on `message` update delivery.
   - `message` must be present in Telegram webhook `allowed_updates`.
   - Current runbooks do not set or assert payment-specific `allowed_updates`.

2. `pre_checkout_query` depends on separate update delivery.
   - `pre_checkout_query` must be present in `allowed_updates`.
   - Current payment smoke runbook does not enforce this.

3. Webhook ACK is durable only up to Celery enqueue, not DB raw-payment storage.
   - If enqueue succeeds and worker later loses the raw payload irrecoverably, Telegram has already received `200`.
   - `processed_updates` cannot replay the original payload because it stores no raw payload.

4. Current update-level idempotency is not payment-event-level inbox.
   - `processed_updates` is keyed by `update_id`; it cannot answer "which payment event had charge_id X?".
   - It does not store `event_type`, `invoice_payload`, `telegram_payment_charge_id`, `user_id`, or raw payment payload.

5. `PAID_UNCREDITED` is not a guaranteed durable checkpoint in normal successful-payment handling.
   - The handler uses one DB transaction around payment marking and crediting.
   - Crash before commit rolls back `PAID_UNCREDITED`, leaving the purchase in `PRECHECKOUT_OK` even though Telegram has paid.

6. Existing recovery only helps if DB already has `PAID_UNCREDITED` with charge id and raw successful payment.
   - It does not recover `PRECHECKOUT_OK` purchases from Telegram Star transactions.
   - It does not call `getStarTransactions`.

7. Current reconciliation is internal-only.
   - It compares DB paid purchases with DB ledger.
   - It cannot see Telegram-side paid transactions missing from DB.

8. Missing payment-specific ambiguous state table/record.
   - Ambiguous Stars transaction matches need a persistent admin/manual-review record, not only logs.

9. Missing exact charge-id conflict handling at service boundary.
   - DB unique constraint prevents two rows with same `telegram_payment_charge_id`, but `PurchaseService.apply_successful_payment()` does not explicitly check whether an incoming charge id belongs to a different purchase before assignment.
   - The resulting DB integrity error would be less auditable than a domain alert/manual review event.

10. `total_amount` validation is weaker than target reliability policy.
    - `_validate_successful_payment_payload()` returns if `total_amount` is `None`.
    - For Telegram Stars paid purchases, target behavior should require `currency="XTR"` and exact `total_amount`.

11. Premium entitlement crediting is not designed for committed partial credit recovery.
    - `entitlement:premium:{purchase.id}` unique key exists.
    - But `_apply_premium_entitlement()` does not first load an existing entitlement by source purchase or idempotency key.
    - If future design commits `PAID_UNCREDITED` and partial assets before crash, crediting must be idempotent at each asset step.

12. Recovery cadence does not meet target threshold.
    - Current `recover_paid_uncredited` runs every 5 minutes with default stale threshold 2 minutes.
    - Target asks for `PAID_UNCREDITED` older than 60 seconds to auto-complete or alert.

13. Observability lacks payment-specific invariant checks.
    - Current alerts cover update processing degradation, recovery review, and internal reconciliation diff.
    - Missing checks listed in this plan below.

14. Production smoke does not assert app-level premium check.
    - Existing sandbox smoke verifies latest purchase status and promo status.
    - It should additionally assert purchase -> ledger -> entitlement -> app-level premium lookup.

## 5. Proposed target architecture

### 5.1 Reliability layers

Use five layers, each idempotent and auditable:

1. Webhook/update durable ingress
   - Store relevant raw Telegram payment updates before acknowledging success, or at minimum before business processing can be considered complete.
   - Recommended table: `telegram_update_inbox`.

2. Payment event inbox
   - Extract payment-specific metadata into a smaller searchable table.
   - Recommended table: `payment_events`.

3. Purchase paid marker
   - For exact successful payment, atomically lock purchase and record:
     - `telegram_payment_charge_id`
     - `raw_successful_payment`
     - `paid_at`
     - `status='PAID_UNCREDITED'`
     - audit event
   - Commit this before asynchronous crediting if the design wants `PAID_UNCREDITED` as a real recovery checkpoint.

4. Idempotent crediting worker
   - One shared path for:
     - webhook `successful_payment`
     - Telegram Star transaction reconciliation
     - stale `PAID_UNCREDITED` recovery
   - Credit assets using idempotency keys and "get existing first" semantics.

5. Telegram Stars reconciliation
   - Poll `getStarTransactions`.
   - Match exact safe transactions and recover them.
   - Alert ambiguous/missing records.

### 5.2 Target state machine

```text
CREATED
  -> INVOICE_SENT
  -> PRECHECKOUT_OK
  -> PAID_UNCREDITED
  -> CREDITED
  -> REFUNDED

Exceptional:
  -> FAILED
  -> FAILED_CREDIT_PENDING_REVIEW
  -> RECONCILIATION_PENDING_REVIEW
```

Rules:

- `PRECHECKOUT_OK` never grants product.
- `PAID_UNCREDITED` means Telegram payment evidence is durably recorded but product crediting is incomplete.
- `CREDITED` means all required assets exist and audit/ledger invariants pass.
- Ambiguous Telegram transaction matching must not credit automatically.

### 5.3 Shared service boundaries

Add or refactor into explicit operations:

```text
PaymentEventService.store_telegram_update(...)
PaymentEventService.extract_payment_event(...)
PurchasePaymentService.mark_paid_from_successful_payment(...)
PurchasePaymentService.mark_paid_from_star_transaction(...)
PurchaseCreditService.credit_paid_purchase(...)
PaymentReconciliationService.reconcile_star_transactions(...)
PaymentInvariantService.check_and_alert(...)
```

Keep public bot UX handlers thin:

- Handler reads Telegram object.
- Handler stores/queues payment event.
- Handler delegates to service/worker.
- Handler never owns DB invariant logic.

## 6. DB constraints and migrations needed

No migration should be applied until implementation is approved. Proposed migrations:

### Migration A - durable Telegram payment inbox

Create `telegram_update_inbox` or extend `processed_updates`.

Recommended new table:

```sql
telegram_update_inbox (
  update_id bigint primary key,
  update_type varchar(64) not null,
  raw_payload jsonb not null,
  received_at timestamptz not null default now(),
  status varchar(32) not null, -- RECEIVED, PROCESSING, PROCESSED, FAILED, DEAD_LETTER
  processing_attempts integer not null default 0,
  last_error_type varchar(128),
  last_error_message text,
  processed_at timestamptz,
  locked_at timestamptz,
  processing_task_id varchar(64)
)
```

Indexes:

- `(status, received_at)`
- partial `(locked_at)` where `status='PROCESSING'`
- GIN on `raw_payload` only if needed for operations; avoid by using `payment_events` for searchable fields.

### Migration B - payment events

Create `payment_events`:

```sql
payment_events (
  id bigserial primary key,
  source varchar(32) not null, -- TELEGRAM_WEBHOOK, TELEGRAM_STARS_RECONCILIATION
  update_id bigint null,
  event_type varchar(64) not null, -- PRE_CHECKOUT, SUCCESSFUL_PAYMENT, REFUNDED_PAYMENT, STAR_TRANSACTION
  status varchar(32) not null, -- RECEIVED, APPLIED, DUPLICATE, AMBIGUOUS, FAILED, DEAD_LETTER
  telegram_user_id bigint,
  user_id bigint,
  purchase_id uuid,
  invoice_payload varchar(128),
  telegram_payment_charge_id varchar(128),
  currency varchar(3),
  total_amount integer,
  transaction_date timestamptz,
  raw_payload jsonb not null,
  idempotency_key varchar(160) not null,
  received_at timestamptz not null default now(),
  applied_at timestamptz,
  last_error_type varchar(128),
  last_error_message text
)
```

Constraints / indexes:

- unique `idempotency_key`
- unique `update_id` where `update_id is not null and event_type in ('SUCCESSFUL_PAYMENT','PRE_CHECKOUT','REFUNDED_PAYMENT')`
- unique `telegram_payment_charge_id` where not null and event_type in (`SUCCESSFUL_PAYMENT`, `STAR_TRANSACTION`)
- index `(status, received_at)`
- index `(invoice_payload)`
- index `(telegram_user_id, total_amount, transaction_date)`
- FK to `purchases(id)` when purchase is resolved.

### Migration C - reconciliation checkpoints and review records

Either extend `reconciliation_runs` or add Stars-specific tables.

Recommended:

```sql
telegram_star_reconciliation_checkpoints (
  id smallint primary key default 1,
  last_offset integer not null default 0,
  last_seen_transaction_id varchar(128),
  updated_at timestamptz not null
)

payment_reconciliation_reviews (
  id bigserial primary key,
  status varchar(32) not null, -- OPEN, RESOLVED, IGNORED
  severity varchar(16) not null, -- HIGH, MEDIUM, LOW
  reason varchar(64) not null,
  telegram_payment_charge_id varchar(128),
  telegram_user_id bigint,
  purchase_id uuid,
  candidates jsonb not null default '[]'::jsonb,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  resolved_at timestamptz,
  resolved_by varchar(128),
  resolution_note text
)
```

Constraints:

- unique open review on `(reason, telegram_payment_charge_id)` where `status='OPEN'` and charge id is present.
- index `(status, severity, created_at)`.

### Migration D - stronger purchase invariants

Existing constraints already cover:

- `purchases.invoice_payload` unique.
- `purchases.telegram_payment_charge_id` unique when not null.
- `purchases.idempotency_key` unique.
- `ledger_entries.idempotency_key` unique.
- `entitlements.idempotency_key` unique.
- active premium per user unique.

Add:

- Unique premium entitlement per source purchase:
  ```sql
  CREATE UNIQUE INDEX uq_entitlements_premium_source_purchase
  ON entitlements(source_purchase_id)
  WHERE entitlement_type='PREMIUM' AND source_purchase_id IS NOT NULL;
  ```
- Optional ledger purchase credit uniqueness:
  ```sql
  CREATE UNIQUE INDEX uq_ledger_purchase_credit_per_purchase
  ON ledger_entries(purchase_id)
  WHERE entry_type='PURCHASE_CREDIT' AND direction='CREDIT' AND purchase_id IS NOT NULL;
  ```
- Optional status/payment check constraints:
  - `paid_at is not null` when status in `('PAID_UNCREDITED','CREDITED','REFUNDED')`.
  - `credited_at is not null` when status in `('CREDITED','REFUNDED')`, except refund of `PAID_UNCREDITED` if that remains allowed.
  - `telegram_payment_charge_id is not null` for paid Stars purchases with `stars_amount > 0` and status in `('PAID_UNCREDITED','CREDITED','REFUNDED')`.

Use data audit/backfill first before adding strict check constraints.

## 7. Telegram Stars reconciliation job design

### 7.1 Source

Use Telegram Bot API `getStarTransactions`.

Runtime config:

- `TELEGRAM_STARS_RECONCILIATION_ENABLED=false` initially.
- `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true` initially.
- `TELEGRAM_STARS_RECONCILIATION_INTERVAL_SECONDS=300` initially; reduce to 60-120 after confidence.
- `TELEGRAM_STARS_RECONCILIATION_LIMIT=100`.
- `TELEGRAM_STARS_RECONCILIATION_LOOKBACK_MINUTES=1440` for initial dry run/backfill; normal mode should use checkpoint/offset plus small overlap.

### 7.2 Cursor / checkpoint

Telegram method uses `offset` and `limit` and returns transactions in chronological order.

Plan:

- Keep `last_offset` and `last_seen_transaction_id`.
- Always re-read a small overlap window or recent N transactions to tolerate offset drift, retention, or concurrent new transactions.
- Deduplicate by `StarTransaction.id`.
- Store every seen payment-related Star transaction in `payment_events` with source `TELEGRAM_STARS_RECONCILIATION`.

Open implementation question:

- Telegram offset semantics can be inconvenient for long-lived cursor if older transactions are retained indefinitely. Confirm exact retention/offset behavior during implementation and prefer idempotent recent-window polling if offset is not operationally stable enough.

### 7.3 Matching algorithm

For each incoming Star transaction:

1. Ignore outgoing/refund transactions for crediting path, but store them for refund/reversal review.
2. If `transaction.id` equals an existing `purchases.telegram_payment_charge_id`:
   - If purchase is `CREDITED`, idempotent no-op.
   - If purchase is `PAID_UNCREDITED`, call crediting recovery.
   - If purchase is `PRECHECKOUT_OK`, `INVOICE_SENT`, or `CREATED`, mark paid and credit only if other facts match.
   - If status is `FAILED`, `FAILED_CREDIT_PENDING_REVIEW`, or `REFUNDED`, create review.
3. If charge id not in DB, match candidates by:
   - Telegram source user id -> `users.telegram_user_id`.
   - `amount == purchases.stars_amount`.
   - `currency == XTR`.
   - `purchases.status in ('PRECHECKOUT_OK','INVOICE_SENT','CREATED')`.
   - time window: purchase created/precheckout time before transaction and within configurable window, e.g. `created_at <= transaction_date <= created_at + 30 minutes`.
   - prefer `PRECHECKOUT_OK` over `INVOICE_SENT` over `CREATED`.
   - product code if derivable from invoice payload/raw metadata; current Telegram StarTransaction does not guarantee invoice payload, so do not require product unless available.
4. Exact safe match:
   - exactly one candidate.
   - same internal user.
   - same amount.
   - status is recoverable.
   - no existing charge id conflict.
   - no open review for same charge id.
5. Ambiguous match:
   - zero candidates but transaction is incoming user payment: high-priority review.
   - more than one candidate: high-priority review.
   - amount/user mismatch: high-priority review.
   - existing conflicting charge id: high-priority review.

### 7.4 Auto-recovery action

For exact safe matches:

```text
lock purchase row
validate still exact
insert/update payment_events row idempotently
write telegram_payment_charge_id if absent
write raw reconciliation payload
write paid_at from transaction date or now_utc with raw transaction date preserved
set status = PAID_UNCREDITED
commit paid marker
enqueue/call shared idempotent crediting path
write audit/outbox event:
  payment_reconciliation_auto_recovered
```

Do not auto-credit ambiguous matches.

### 7.5 Handling the incident class

For DB purchase stuck in `PRECHECKOUT_OK` older than 3 minutes:

- Reconciliation sees Telegram transaction with user id `270`, amount `29`, transaction date close to purchase creation/precheckout, product `PREMIUM_WEEK` by DB row.
- If exactly one match:
  - fill `telegram_payment_charge_id`.
  - store raw transaction payload.
  - move to `PAID_UNCREDITED`.
  - call shared crediting path.
  - result should create premium entitlement and ledger, then set `CREDITED`.

## 8. Durable inbox/outbox decision

Decision: add a durable payment inbox; do not rely only on `processed_updates`.

Reason:

- `processed_updates` is good for update idempotency but does not contain raw payload.
- Payment reliability requires replay after worker crash, dead-letter review, and correlation by charge id/invoice payload/user.
- Telegram will not retry after the webhook returns `200`; therefore the app must durably own the event before returning `200` or have an equivalent durable broker guarantee plus raw payload store.

Recommended implementation shape:

1. In `telegram_webhook()`, after JSON parse and `update_id` extraction:
   - Detect payment-relevant update types cheaply:
     - `pre_checkout_query`
     - `message.successful_payment`
     - `message.refunded_payment` if supported by aiogram/model
   - For all update types, existing Celery enqueue can remain.
   - For payment-relevant update types, synchronously insert `telegram_update_inbox` and `payment_events` before returning `200`.
2. Duplicate update:
   - `ON CONFLICT(update_id) DO NOTHING` / idempotent update.
   - Return `200` if already stored/enqueued.
3. If DB insert of payment update fails:
   - Return `503 {"status":"retry"}` so Telegram retries.
4. Worker:
   - Processes from `payment_events` or from raw `telegram_update_inbox`.
   - Marks event status `APPLIED`, `DUPLICATE`, `FAILED`, or `DEAD_LETTER`.
5. Outbox:
   - Continue using `outbox_events` and `send_ops_alert`.
   - Add payment-specific reliability events.

Alternative:

- Extend `processed_updates` with `raw_payload`, `update_type`, and payment metadata.
- This reduces table count but overloads a table currently used as short-retention update status. A separate payment inbox is cleaner because payment audit retention should be longer than generic update retention.

## 9. Alerting / monitoring plan

### 9.1 Production checks

Add a read-only invariant script, e.g. `scripts/payment_reliability_checks.py`, with SQL checks:

1. `PRECHECKOUT_OK` older than 3 minutes for paid product.
2. `PAID_UNCREDITED` older than 60 seconds.
3. `CREDITED` premium purchase without entitlement where `entitlements.source_purchase_id = purchases.id`.
4. `paid_at IS NOT NULL AND credited_at IS NULL AND status != 'PAID_UNCREDITED'`.
5. `telegram_payment_charge_id IS NOT NULL AND status != 'CREDITED' AND status != 'REFUNDED'`.
6. Duplicate `telegram_payment_charge_id`.
7. Duplicate active premium entitlements per user.
8. Credited Stars purchase missing `PURCHASE_CREDIT` ledger row.
9. Manual compensation/recovery without admin audit/review record.
10. `payment_events` failed/dead-letter count > 0 in last 15 minutes.
11. `payment_reconciliation_reviews.status='OPEN'`.
12. Telegram reconciliation diff > 0.
13. Telegram webhook `pending_update_count` > 0 and growing.
14. Telegram webhook `last_error_date` / `last_error_message` present in current deploy/incident window.
15. `getStarTransactions` poll failure or stale checkpoint older than 10 minutes.

### 9.2 Alert events

Add ops alert event names:

- `payments_precheckout_stuck_detected`
- `payments_paid_uncredited_stuck_detected`
- `payments_credit_invariant_failed`
- `payments_telegram_star_reconciliation_failed`
- `payments_telegram_star_auto_recovered`
- `payments_telegram_star_review_required`
- `payments_payment_event_dead_lettered`
- `payments_webhook_allowed_updates_missing`

Severity:

- HIGH:
  - Telegram paid transaction with no DB purchase.
  - `PRECHECKOUT_OK` exact paid match not credited.
  - `PAID_UNCREDITED` older than 60 seconds and recovery failed.
  - missing premium entitlement for credited premium purchase.
- MEDIUM:
  - ambiguous reconciliation match.
  - internal reconciliation diff.
  - stale checkpoint.
- LOW:
  - single retryable payment event failure that recovered.

### 9.3 Logs

Add structured logs with redacted/minimal payload:

- `payment_successful_update_received`
- `payment_successful_mark_paid_started`
- `payment_successful_mark_paid_finished`
- `payment_credit_started`
- `payment_credit_finished`
- `payment_credit_failed`
- `payment_reconciliation_transaction_seen`
- `payment_reconciliation_auto_recovered`
- `payment_reconciliation_ambiguous`

Include:

- `update_id`
- `purchase_id`
- `user_id`
- `telegram_user_id`
- `product_code`
- `stars_amount`
- `telegram_payment_charge_id`
- `invoice_payload_hash`, not raw payload if not needed in logs.

Avoid:

- Full bot token, webhook secret, headers, or full raw update dumps in logs.

## 10. Test matrix

### 10.1 Happy path

1. `Premium Week successful payment creates entitlement`
   - `PREMIUM_WEEK`, `29 XTR`.
   - Assert purchase `CREDITED`, ledger row, active premium entitlement for 7 days.
2. `Premium Month successful payment creates entitlement`
   - `PREMIUM_MONTH`, `99 XTR`.
   - Assert purchase `CREDITED`, ledger row, active entitlement for 30 days.
3. `Premium upgrade extends correctly`
   - Existing lower plan, buy higher plan.
   - Assert old entitlement revoked, new entitlement extends from existing end.
4. `Duplicate successful_payment is idempotent`
   - Same `update_id` and same `telegram_payment_charge_id`.
   - Assert one ledger row and one entitlement from purchase.
5. `Duplicate charge id on different invoice is blocked`
   - Same `telegram_payment_charge_id`, different purchase.
   - Assert no second credit, review/alert created.

### 10.2 Webhook failure path

1. `pre_checkout_query OK but no successful_payment`
   - Assert no entitlement.
   - Assert purchase becomes detectable as stale `PRECHECKOUT_OK`.
2. `successful_payment handler receives update but crashes before crediting`
   - Durable inbox has raw update/payment event.
   - Retry/worker recovers and credits.
3. `successful_payment marks PAID_UNCREDITED then crashes before entitlement`
   - Durable paid marker is committed.
   - Recovery completes crediting.
4. `Telegram sends duplicate update`
   - Duplicate `telegram_update_inbox`/`payment_events` is safe.
   - No duplicate entitlement/ledger.
5. `Celery enqueue fails after payment update received`
   - If payment inbox insert failed, webhook returns `503`.
   - If payment inbox insert succeeded but Celery enqueue failed, follow-up inbox worker still processes event.
6. `Dispatcher raises unexpected exception in payment handler`
   - Update status becomes `FAILED`.
   - Payment event remains retryable/dead-lettered with alert after max retries.

### 10.3 Reconciliation path

1. `Telegram Star transaction exists, DB purchase PRECHECKOUT_OK`
   - Exact match auto-credits.
2. `Telegram Star transaction exists, DB purchase missing charge_id`
   - Fill `telegram_payment_charge_id`, store raw reconciliation payload, credit.
3. `Telegram Star transaction amount mismatch`
   - No auto-credit.
   - Admin review/alert.
4. `Telegram Star transaction user mismatch`
   - No auto-credit.
   - Admin review/alert.
5. `Two possible purchases match same transaction`
   - No auto-credit.
   - Admin review with candidates.
6. `Purchase already credited`
   - Reconciliation idempotent no-op.
7. `Stale PAID_UNCREDITED`
   - Recovery finishes crediting or marks review after retry threshold.
8. `Telegram transaction exists but DB has no purchase`
   - High-priority review/alert.
9. `Outgoing/refund Star transaction`
   - Stored, not credited through incoming purchase path.

### 10.4 Refund path

1. `Refunded payment revokes entitlement or records refund state correctly`
   - Existing `PurchaseService.refund_purchase` behavior remains idempotent.
2. `refundStarPayment path requires valid telegram_payment_charge_id`
   - No refund call without charge id.
3. `Refund after manual compensation`
   - Explicit review/audit record required because compensated entitlement may not map to original purchase.
4. `Refund of PAID_UNCREDITED`
   - Does not require missing credit ledger.
   - Marks purchase `REFUNDED` and emits audit event.

### 10.5 Production smoke tests

1. Mock Telegram `pre_checkout_query`.
2. Mock Telegram `message.successful_payment`.
3. Assert:
   - purchase row transitions through expected state.
   - ledger row exists.
   - premium entitlement exists.
   - `EntitlementsRepo.has_active_premium(...)` returns true.
   - duplicate replay does not duplicate ledger/entitlement.
4. Run before monetization deploy.
5. Verify webhook `allowed_updates` contains at least:
   - `message`
   - `pre_checkout_query`
   - optionally `my_chat_member` for block/unblock status.

## 11. Safe rollout plan

### Phase 1 - Read-only audit and tests

No production writes.

Deliverables:

- Add tests for known failure class:
  - DB purchase `PRECHECKOUT_OK`, Telegram transaction exists, no successful_payment update persisted.
  - Existing current behavior should fail or only alert in dry-run until implementation lands.
- Add read-only invariant queries/script.
- Add test fixtures for Telegram `StarTransaction`.
- Add tests for strict successful payment payload validation.
- Add tests for allowed_updates check function.

Files likely changed:

- `tests/economy/test_purchase_credit_service.py`
- `tests/integration/test_purchase_premium_integration.py`
- `tests/integration/test_payments_idempotency_reconciliation_integration.py`
- `tests/workers/test_payments_reliability_*.py`
- new `tests/services/test_telegram_stars_reconciliation.py`
- new `scripts/payment_reliability_checks.py`

### Phase 2 - Observability

No auto-recovery from Telegram yet.

Deliverables:

- Structured logs around successful payment mark-paid and credit.
- Payment-specific stuck checks:
  - `PRECHECKOUT_OK > 3m`
  - `PAID_UNCREDITED > 60s`
  - credited premium without entitlement.
- Ops alerts for high-severity invariants.
- Production runbook update to assert payment `allowed_updates`.

Files likely changed:

- `app/bot/handlers/payments.py`
- `app/bot/handlers/payments_runtime.py`
- `app/workers/tasks/payments_reliability_async.py`
- `app/workers/tasks/payments_reliability_schedule.py`
- `app/services/payments_reliability.py`
- `docs/operations/production_state_checks.md`
- `docs/runbooks/telegram_sandbox_stars_smoke.md`

### Phase 3 - Reconciliation dry-run

No production crediting from Telegram transactions yet.

Deliverables:

- Implement Telegram `getStarTransactions` client wrapper.
- Store checkpoint and dry-run comparison.
- Create review records for ambiguous/missing cases in dry-run.
- Compare Telegram incoming Stars totals against DB paid totals.
- Alert if dry-run would recover anything.

Files likely changed:

- new `app/services/telegram_stars.py`
- new `app/services/payment_reconciliation.py`
- `app/workers/tasks/payments_reliability_reconciliation.py`
- `app/workers/tasks/payments_reliability_schedule.py`
- `app/core/config_messaging.py` or relevant config mixin
- `.env.example` and `.env.production.example` only after explicit approval because config templates are protected/sensitive.
- new Alembic migration for checkpoint/review tables after approval.

### Phase 4 - Controlled auto-recovery

Enable auto-credit only for exact safe matches.

Rules:

- Auto-credit only when one candidate matches by charge/user/amount/time/status.
- Ambiguous cases remain manual review.
- Dry-run metrics must be clean for a defined soak window before enabling.
- Feature flag controls:
  - `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=false`
  - optional `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=true`

Files likely changed:

- `app/economy/purchases/service/credit.py`
- `app/economy/purchases/service/credit_assets.py`
- `app/economy/purchases/service/entitlements.py`
- `app/workers/tasks/payments_reliability_async.py`
- `app/services/payment_reconciliation.py`
- integration tests for exact/ambiguous auto-recovery.

### Phase 5 - Hardening

Deliverables:

- Add durable inbox/outbox migration if not already delivered in Phase 3.
- Strengthen DB constraints after data audit.
- Make asset crediting "get existing first" idempotent.
- Add production smoke test gate before each payment deploy.
- Add runbook for manual review and compensation.
- Add rollback plan for flags without schema rollback.

Files likely changed:

- `app/db/models/payment_events.py`
- `app/db/models/telegram_update_inbox.py`
- `app/db/models/payment_reconciliation_reviews.py`
- `app/db/repo/*payment*`
- `alembic/versions/<new>_payment_reliability_inbox.py`
- `alembic/versions/<new>_payment_reliability_constraints.py`
- `docs/runbooks/payment_reliability.md`
- `scripts/payment_smoke.py` or similar.

## 12. Backward compatibility risks

1. Existing purchases without `telegram_payment_charge_id`
   - Strict new constraints need data audit first.
   - Do not add strict check constraints until historical rows are classified.

2. Existing zero-cost premium/promo rows
   - `stars_amount=0` products exist (`PREMIUM_3_DAYS` soft-disabled but used for grants/promos).
   - Paid Stars constraints must apply only to `stars_amount > 0`.

3. Active premium uniqueness
   - Existing partial unique active premium per user means upgrade logic must keep revoke/create order correct.
   - Recovery logic must not accidentally create duplicate active premium rows.

4. Payment handler UX
   - If handler returns failure text while recovery later credits, user may see an error then receive product.
   - Target behavior should prefer "payment received, processing" for uncertain failures once durable event exists.

5. Telegram API / aiogram object model drift
   - Confirm aiogram version supports `get_star_transactions` or use raw Bot API request wrapper.
   - Confirm `refunded_payment` field support before relying on it in typed handlers.

6. Webhook `allowed_updates`
   - Setting a restrictive list can accidentally drop unrelated bot flows.
   - Required minimum for payment reliability: include `message`, `callback_query`, `pre_checkout_query`; add `my_chat_member` if block/unblock status is used.

7. Retention
   - Generic update retention may be shorter than payment audit retention.
   - Payment event retention should be long enough for disputes/refunds/accounting.

## 13. Production validation checklist

Before enabling payment reliability changes:

- Confirm local tests:
  - `make lint`
  - `make format-check`
  - `make type-check`
  - `pytest -q --ignore=tests/integration`
  - targeted integration tests for payments/reconciliation.
- Confirm migration review:
  - schema constraints are backward-compatible.
  - data audit queries are clean or migration handles old rows.
- Confirm webhook:
  - URL is `https://deutchquizarena.de/webhook/telegram`.
  - `allowed_updates` includes `message`, `callback_query`, `pre_checkout_query`.
  - `pending_update_count` is low/not growing.
  - no fresh `last_error_message`.
- Confirm workers:
  - `q_high` and `q_normal` not growing.
  - payment reconciliation task registered in Celery.
  - beat schedule loaded.
- Run production/staging payment smoke:
  - mock or sandbox `pre_checkout_query`.
  - mock or sandbox `successful_payment`.
  - assert purchase -> ledger -> entitlement -> active premium lookup.
- Dry-run reconciliation:
  - no unexpected unmatched paid transactions.
  - checkpoint fresh.
  - alerts reachable.
- Feature flags:
  - deploy with dry-run first.
  - enable auto-recovery only after dry-run soak.

## 14. Files proposed for future changes

### Existing files

- `app/api/routes/telegram_webhook.py`
  - Insert durable inbox path for payment updates before `200`.
  - Preserve `503` on failed durable write/enqueue.
- `app/services/telegram_updates.py`
  - Add update type/payment metadata extraction helpers or move to new payment inbox service.
- `app/workers/tasks/telegram_updates_processing.py`
  - Route durable inbox processing/retry if extending generic update pipeline.
- `app/bot/handlers/payments.py`
  - Add structured payment logs and unexpected exception alerting.
  - Keep handlers thin.
- `app/bot/handlers/payments_runtime.py`
  - Pass `update_id`/payment event id if available.
- `app/economy/purchases/service/credit.py`
  - Split mark-paid from crediting if using durable `PAID_UNCREDITED`.
  - Require exact `currency`, `total_amount`, `invoice_payload`, `telegram_payment_charge_id`.
  - Explicitly reject charge-id conflict.
- `app/economy/purchases/service/credit_assets.py`
  - Make asset crediting safe for re-entry after partial progress.
  - Check existing ledger by idempotency key before create, or use insert-on-conflict semantics.
- `app/economy/purchases/service/entitlements.py`
  - Check existing entitlement by idempotency/source purchase before create.
- `app/db/repo/purchases_repo.py`
  - Add queries for stale `PRECHECKOUT_OK`, charge-id lookup, exact match candidates.
- `app/db/repo/entitlements_repo.py`
  - Add get-by-source-purchase/idempotency helper.
- `app/db/repo/ledger_repo.py`
  - Add idempotent create/get helpers for purchase credits.
- `app/workers/tasks/payments_reliability_async.py`
  - Lower `PAID_UNCREDITED` target threshold to 60 seconds via config.
  - Integrate shared crediting recovery.
- `app/workers/tasks/payments_reliability_reconciliation.py`
  - Add Telegram Stars reconciliation or delegate to new service.
- `app/workers/tasks/payments_reliability_schedule.py`
  - Add 1-5 minute Stars reconciliation schedule.
- `app/services/payments_reliability.py`
  - Add invariant checks and matching helpers if not moved to a new service.
- `app/services/alerts.py`
  - Reuse existing alert sending; likely no core change unless routing/severity needs extension.
- `app/core/config_messaging.py`
  - Add reconciliation feature flags and thresholds.
- `docs/runbooks/telegram_sandbox_stars_smoke.md`
  - Add `allowed_updates` and purchase -> entitlement -> premium lookup checks.
- `docs/operations/production_state_checks.md`
  - Add payment reliability invariant checks.
- `docs/analytics/events_catalog.md`
  - Add new payment ops alert/outbox events.

### New files

- `app/services/telegram_stars.py`
  - Bot API wrapper for `getStarTransactions` and possibly `refundStarPayment`.
- `app/services/payment_events.py`
  - Store/extract payment events from webhook/reconciliation payloads.
- `app/services/payment_reconciliation.py`
  - Matching algorithm and dry-run/auto-recovery decisions.
- `app/db/models/payment_events.py`
- `app/db/models/telegram_update_inbox.py`
- `app/db/models/payment_reconciliation_reviews.py`
- `app/db/models/telegram_star_reconciliation_checkpoints.py`
- `app/db/repo/payment_events_repo.py`
- `app/db/repo/telegram_update_inbox_repo.py`
- `app/db/repo/payment_reconciliation_reviews_repo.py`
- `app/db/repo/telegram_star_reconciliation_checkpoints_repo.py`
- `scripts/payment_reliability_checks.py`
- `docs/runbooks/payment_reliability.md`
- `tests/services/test_payment_reconciliation.py`
- `tests/services/test_payment_events.py`
- `tests/workers/test_telegram_stars_reconciliation_task.py`
- `tests/integration/test_payment_reliability_inbox_integration.py`
- `tests/integration/test_telegram_stars_reconciliation_integration.py`

### Alembic migrations after approval

- `<new>_payment_events_and_update_inbox.py`
- `<new>_telegram_stars_reconciliation_tables.py`
- `<new>_payment_crediting_constraints.py`

## 15. Open questions requiring owner decision

1. Should `PAID_UNCREDITED` be committed before crediting?
   - Recommended: yes, if recovery must complete crediting after crash between paid marker and asset grant.
   - Cost: asset crediting must be fully idempotent at every step.

2. Should webhook store all updates or only payment-relevant updates?
   - Recommended: store all updates in generic inbox only if operational cost is acceptable; otherwise store payment-relevant updates in `payment_events` synchronously and keep generic `processed_updates` for non-payment idempotency.

3. Payment audit retention period?
   - Recommended: longer than generic updates; at least enough for refunds/disputes/accounting.

4. Manual compensation model?
   - Need explicit admin audit schema for "manual PREMIUM_MONTH compensation because original PREMIUM_WEEK failed".
   - Decide whether manual compensation links to original purchase, separate grant, or review record.

5. Auto-recovery enablement gate?
   - Recommended: dry-run with zero unexpected ambiguous matches for a defined period, then exact-match auto-credit only.

6. Telegram client implementation?
   - If current aiogram lacks typed `get_star_transactions`, use a minimal internal HTTP wrapper with Bot API token, timeouts, and structured errors.

7. Refund policy after compensation?
   - Decide whether refunding original payment revokes compensation, leaves compensation intact, or requires manual review.

## 16. Risk assessment

High risk if not fixed:

- Any lost `message.successful_payment` can leave a paid user without product and without DB paid evidence.
- Internal reconciliation cannot detect Telegram-paid/DB-unpaid gaps.

Medium implementation risk:

- Splitting mark-paid and crediting introduces partial states by design; all asset crediting must become idempotent.
- New strict constraints can fail on historical data unless audited first.

Low operational risk with phased rollout:

- Observability and dry-run reconciliation are read-only/safe.
- Auto-recovery can be feature-flagged and limited to exact matches.

## 17. Anything still unknown

- Current production code at `/opt/quiz-arena` could not be inspected here.
- Current production webhook `allowed_updates` could not be verified without production token/access.
- Exact incident row contents were provided in the task but not queried from production DB, by instruction.
- Current aiogram version support for Stars transaction methods needs implementation-time verification.
