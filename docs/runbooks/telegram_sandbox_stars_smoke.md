# Telegram Sandbox Stars Smoke Runbook

## Scope

Sandbox/staging smoke for Telegram Stars purchase flow and callback replay safety.

Covers:
- promo discount redeem -> purchase -> pre-checkout -> successful credit,
- referral reward callback duplicate replay safety.

Do not run this runbook against production unless the production owner has approved a payment
smoke window. The cleanup step mutates sandbox/staging promo data.

## Preconditions

- Use sandbox/staging environment (not production campaign codes).
- Public HTTPS webhook endpoint is reachable.
- Services are running: API, worker, Redis, Postgres.
- `.env` contains valid:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_WEBHOOK_SECRET`
  - `DATABASE_URL`, `REDIS_URL`, `CELERY_*`
- Python venv is ready.

Recommended shell setup:

```bash
cd /opt/quiz-arena
source .env
export PUBLIC_WEBHOOK_BASE="<https://your-public-host>"
```

## 1) Prepare temporary promo campaign

Generate a short-lived sandbox discount batch:

```bash
VALID_FROM=$(date -u -d '-1 day' +%Y-%m-%dT%H:%M:%S+00:00)
VALID_UNTIL=$(date -u -d '+7 day' +%Y-%m-%dT%H:%M:%S+00:00)

PYTHONPATH=. .venv/bin/python scripts/promo_batch_tool.py \
  --campaign-name sandbox_smoke_discount_50 \
  --promo-type PERCENT_DISCOUNT \
  --discount-percent 50 \
  --target-scope PREMIUM_MONTH \
  --valid-from "$VALID_FROM" \
  --valid-until "$VALID_UNTIL" \
  --max-total-uses 100 \
  --created-by smoke_runbook \
  --count 3 \
  --prefix SMOKE \
  --output-csv /tmp/smoke_discount_codes.csv
```

Use one generated code in Telegram scenario A.

## 2) Bind webhook

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_WEBHOOK_BASE}/webhook/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  --data-urlencode 'allowed_updates=["message","callback_query","pre_checkout_query","my_chat_member"]'

curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
  > /tmp/telegram_webhook_info.json

PYTHONPATH=. .venv/bin/python scripts/payment_reliability_checks.py \
  --skip-db \
  --webhook-info-json /tmp/telegram_webhook_info.json
```

Expected:
- webhook URL points to `${PUBLIC_WEBHOOK_BASE}/webhook/telegram`,
- `payment_reliability_checks` reports `payments_webhook_allowed_updates_missing` as `OK`,
- `allowed_updates` contains at least `message`, `callback_query`, and `pre_checkout_query`,
- `pending_update_count` не росте; якщо є `last_error_message`, тоді `last_error_date` має бути до початку поточного smoke.

## 3) Scenario A: promo discount -> Stars purchase

In Telegram:
1. Send `/promo <CODE_FROM_STEP_1>`.
2. Tap promo CTA button.
3. Confirm Stars purchase.
4. Verify success message from bot.

### 3.1 DB validation

Find user:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, telegram_user_id from users where telegram_user_id = <tg_user_id>;"
```

Check latest redemption/purchase:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select status, reserved_until, applied_purchase_id \
 from promo_redemptions \
 where user_id = <user_id> \
 order by created_at desc \
 limit 1;"

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, status, product_code, base_stars_amount, discount_stars_amount, stars_amount, \
        paid_at, credited_at \
 from purchases \
 where user_id = <user_id> \
 order by created_at desc \
 limit 1;"
```

Expected:
- latest `promo_redemptions.status='APPLIED'`,
- latest `purchases.status='CREDITED'`,
- latest purchase has non-null `paid_at` and `credited_at`,
- `discount_stars_amount > 0`.

Check purchase credit ledger, premium entitlement, and the app-level premium lookup:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select entry_type, direction, amount, metadata_->>'product_code' as product_code \
 from ledger_entries \
 where purchase_id = '<purchase_id>' and entry_type = 'PURCHASE_CREDIT' \
 order by created_at desc;"

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select entitlement_type, scope, status, starts_at, ends_at \
 from entitlements \
 where source_purchase_id = '<purchase_id>' and user_id = <user_id> \
 order by created_at desc;"

SMOKE_USER_ID=<user_id> PYTHONPATH=. .venv/bin/python - <<'PY'
import asyncio
import os
from datetime import datetime, timezone

from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        active = await EntitlementsRepo.has_active_premium(
            session,
            int(os.environ["SMOKE_USER_ID"]),
            datetime.now(timezone.utc),
        )
    print(f"active_premium={active}")


asyncio.run(main())
PY
```

Expected:
- exactly one `PURCHASE_CREDIT` ledger row for the smoke purchase,
- an `ACTIVE` `PREMIUM` entitlement exists for `source_purchase_id='<purchase_id>'`,
- app-level lookup prints `active_premium=True`.

### 3.2 Payment reliability checks

```bash
PYTHONPATH=. .venv/bin/python scripts/payment_reliability_checks.py \
  --webhook-info-json /tmp/telegram_webhook_info.json
```

Expected:
- `payments_precheckout_stuck_detected` is `OK`,
- `payments_paid_uncredited_stuck_detected` is `OK`,
- `payments_credited_premium_missing_entitlement` is `OK`,
- `payments_credited_stars_missing_purchase_credit` is `OK`,
- `payments_constraint_duplicate_premium_source_purchase` is `OK`,
- `payments_constraint_duplicate_purchase_credit_ledger` is `OK`,
- `payments_constraint_paid_purchase_missing_charge_id` is `OK`,
- `payments_constraint_paid_purchase_missing_paid_at` is `OK`,
- `payments_constraint_credited_purchase_missing_credited_at` is `OK`,
- `payments_open_manual_review_records` is `OK`,
- `payments_webhook_allowed_updates_missing` is `OK`.

These `payments_constraint_*` rows are read-only migration preflight checks. They do not create or
enforce constraints; production constraints require a separate approved migration after clean data
audit. The `credited_at` preflight requires timestamps for `CREDITED` purchases and for `REFUNDED`
purchases with credit evidence, but it intentionally allows a purchase refunded from
`PAID_UNCREDITED` before crediting to keep `credited_at IS NULL`.

Confirm reliability flags are still safe unless an explicit dry-run or auto-recovery window was
approved:

```bash
printf 'TELEGRAM_STARS_RECONCILIATION_ENABLED=%s\n' "${TELEGRAM_STARS_RECONCILIATION_ENABLED:-false}"
printf 'TELEGRAM_STARS_RECONCILIATION_DRY_RUN=%s\n' "${TELEGRAM_STARS_RECONCILIATION_DRY_RUN:-true}"
printf 'TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=%s\n' "${TELEGRAM_STARS_AUTO_RECOVERY_ENABLED:-false}"
```

Expected default-safe values:
- `TELEGRAM_STARS_RECONCILIATION_ENABLED=false`,
- `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true`,
- `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false`.

Rollback for reconciliation issues:
- set `TELEGRAM_STARS_RECONCILIATION_ENABLED=false`,
- keep `TELEGRAM_STARS_RECONCILIATION_DRY_RUN=true`,
- set `TELEGRAM_STARS_AUTO_RECOVERY_ENABLED=false`,
- restart only the approved app services for the target environment,
- schema rollback є окремим owner-approved release rollback рішенням; цей smoke rollback
  використовує safe/off flags і не мутує production payment data.

Check that the Stars reconciliation dry-run did not leave open review findings:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, created_at, payload->>'reason' as reason, payload->>'severity' as severity, \
        payload->>'transaction_id_hash' as transaction_id_hash, \
        payload->>'transaction_amount' as transaction_amount, \
        payload->>'transaction_date' as transaction_date, \
        payload->>'telegram_user_id' as telegram_user_id, \
        payload->'candidate_purchase_ids' as candidate_purchase_ids \
 from outbox_events \
 where event_type='payments_telegram_stars_reconciliation_review' and status='OPEN' \
 order by created_at desc, id desc \
 limit 20;"
```

Expected:
- no open rows for a healthy sandbox smoke,
- any open row is reviewed manually before compensation/recovery,
- payload contains hashes, amount/date/user clues, and candidate purchase ids only, not a raw token,
  invoice payload, charge id, or Telegram transaction payload,
- `OPEN` review rows are retained until manually resolved and are not removed by age-based
  outbox retention cleanup.

Check dedicated payment validation reviews:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, created_at, review_type, severity, reason, purchase_id, transaction_id_hash, \
        safe_payload->>'telegram_payment_charge_id_hash' as payment_charge_hash, status \
 from payment_reconciliation_reviews \
 where status='OPEN' \
 order by created_at desc, id desc \
 limit 20;"
```

Expected:
- немає open rows для здорового sandbox smoke,
- будь-який open row блокує automatic credit/recovery до owner review,
- rows містять тільки hashes і safe purchase/user references.

Confirm payment webhook evidence persisted before ACK:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select update_id, received_at, update_kind, status, \
        sanitized_evidence->>'payment_update_kind' as payment_update_kind, payload_hash \
 from telegram_update_inbox \
 order by received_at desc, update_id desc \
 limit 20;"
```

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, provider, event_type, invoice_payload, provider_charge_id_hash, \
        currency, total_amount, source_inbox_update_id \
 from payment_events \
 order by created_at desc, id desc \
 limit 20;"
```

Expected:
- smoke payment має `pre_checkout_query` і `message.successful_payment` inbox/event rows,
- rows збережені до того, як webhook повертає `200` або enqueue succeeds,
- evidence зберігає тільки sanitized fields і hashes; без raw order info, email, phone, shipping
  details, raw charge ids, request headers або webhook secrets.

## 4) Scenario B: referral reward callback replay

1. Ensure a referrer has claimable reward state.
2. Tap reward callback button once.
3. Replay same callback (duplicate tap/retry).

### 4.1 DB validation

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select status, count(*) \
 from referrals \
 where referrer_user_id = <user_id> \
 group by status;"

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select entry_type, asset, source, count(*) \
 from ledger_entries \
 where user_id = <user_id> and source = 'REFERRAL' \
 group by entry_type, asset, source;"
```

Expected:
- no duplicate reward credit from callback replay,
- exactly one valid reward transition for the tested action.

## 5) Cleanup

Disable webhook if smoke session is over:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

Expire temporary sandbox campaigns:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"update promo_codes \
 set status = 'EXPIRED', updated_at = now() \
 where campaign_name like 'sandbox_smoke_%' and status = 'ACTIVE';"
```
