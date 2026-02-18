# Telegram Sandbox Stars Smoke Runbook

## Goal
- Validate real Telegram Bot API + Stars payment path on sandbox/staging infra.
- Cover:
  - promo discount redeem -> purchase -> pre-checkout -> successful payment credit;
  - referral reward choice callback replay safety.

## Preconditions
- Public HTTPS endpoint for `/webhook/telegram` (for example via tunnel).
- Running services:
  - API (`app.main`);
  - worker (`celery ... worker`);
  - Redis + Postgres.
- `.env` configured with valid:
  - `TELEGRAM_BOT_TOKEN`;
  - `TELEGRAM_WEBHOOK_SECRET`;
  - `DATABASE_URL`, `REDIS_URL`, `CELERY_*`.

## 1) Prepare promo campaign
Use CLI tool to generate/import a temporary sandbox campaign:

```bash
PYTHONPATH=. .venv/bin/python scripts/promo_batch_tool.py \
  --campaign-name sandbox_smoke_discount_50 \
  --promo-type PERCENT_DISCOUNT \
  --discount-percent 50 \
  --target-scope PREMIUM_MONTH \
  --valid-from 2026-02-18T00:00:00+00:00 \
  --valid-until 2026-03-01T00:00:00+00:00 \
  --max-total-uses 100 \
  --created-by smoke_runbook \
  --count 3 \
  --prefix SMOKE \
  --output-csv /tmp/smoke_discount_codes.csv
```

Take one generated code for the Telegram scenario.

## 2) Bind webhook to Telegram

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${PUBLIC_WEBHOOK_BASE}/webhook/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

Optional check:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

## 3) Scenario A: promo discount -> Stars purchase
1. In Telegram chat with bot send: `/promo <CODE_FROM_STEP_1>`.
2. Tap promo discount CTA button (contains promo-bound callback).
3. Confirm Telegram Stars purchase.
4. Verify bot sends successful purchase text.

DB validation (replace `<tg_user_id>`):

```sql
select id from users where telegram_user_id = <tg_user_id>;

select status, reserved_until, applied_purchase_id
from promo_redemptions
where user_id = <user_id>
order by created_at desc
limit 1;

select status, product_code, base_stars_amount, discount_stars_amount, stars_amount
from purchases
where user_id = <user_id>
order by created_at desc
limit 1;
```

Expected:
- latest `promo_redemptions.status = 'APPLIED'`;
- latest `purchases.status = 'CREDITED'`;
- `discount_stars_amount > 0`.

## 4) Scenario B: referral reward choice duplicate replay
1. Ensure referrer has claimable reward slot (3 qualified referrals, reward delay elapsed).
2. In Telegram tap reward choice button once (`referral:reward:MEGA_PACK_15` or `PREMIUM_STARTER`).
3. Replay same callback (button retry or scripted duplicate callback).

DB validation:

```sql
select status, count(*)
from referrals
where referrer_user_id = <user_id>
group by status;

select entry_type, asset, source, count(*)
from ledger_entries
where user_id = <user_id>
  and source = 'REFERRAL'
group by entry_type, asset, source;
```

Expected:
- exactly one newly rewarded slot for duplicated callback replay;
- no duplicate reward credits in ledger.

## 5) Cleanup
Disable webhook if run is complete:

```bash
curl -sS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteWebhook"
```

Expire sandbox promo campaigns if needed:

```sql
update promo_codes
set status = 'EXPIRED', updated_at = now()
where campaign_name like 'sandbox_smoke_%' and status = 'ACTIVE';
```
