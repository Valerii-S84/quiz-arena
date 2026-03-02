# Telegram Sandbox Stars Smoke Runbook

## Scope

Sandbox/staging smoke for Telegram Stars purchase flow and callback replay safety.

Covers:
- promo discount redeem -> purchase -> pre-checkout -> successful credit,
- referral reward callback duplicate replay safety.

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
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"

curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Expected:
- webhook URL points to `${PUBLIC_WEBHOOK_BASE}/webhook/telegram`,
- no `last_error_message`.

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
"select status, product_code, base_stars_amount, discount_stars_amount, stars_amount \
 from purchases \
 where user_id = <user_id> \
 order by created_at desc \
 limit 1;"
```

Expected:
- latest `promo_redemptions.status='APPLIED'`,
- latest `purchases.status='CREDITED'`,
- `discount_stars_amount > 0`.

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
