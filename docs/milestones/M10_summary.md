# M10 Summary

## Implemented
- Added promo code crypto helpers:
  - normalization (trim/uppercase/remove spaces and hyphens),
  - HMAC-SHA256 hashing with `PROMO_SECRET_PEPPER`.
- Added promo redeem domain service:
  - idempotency by `promo_redemptions.idempotency_key`;
  - `PREMIUM_GRANT` flow (entitlement + ledger + used_total increment);
  - `PERCENT_DISCOUNT` flow (15-minute reservation).
- Added internal API endpoint:
  - `POST /internal/promo/redeem`.
- Added anti-abuse controls:
  - per-user failed-attempt throttling (5/24h + 60m block behavior),
  - global brute-force guard that auto-pauses abused active campaigns.
- Added scheduled promo jobs:
  - reservation expiry (`RESERVED` -> `EXPIRED`);
  - campaign rollover (`ACTIVE` -> `EXPIRED`/`DEPLETED`);
  - brute-force guard autopause.
- Added bot promo entry flow:
  - `/promo <code>` command,
  - `promo:open` callback hint,
  - German success/error texts for promo outcomes;
  - discount purchase CTA keyboard with `promo_redemption_id` callback wiring.
- Added promo batch admin tooling:
  - `scripts/promo_batch_tool.py` supports code generation and CSV import,
  - writes normalized output report with inserted `promo_code_id`.
- Added provider-specific alert routing:
  - event -> channel/severity/tier templates for `generic`, `slack`, `pagerduty`;
  - policy overrides via `OPS_ALERT_ESCALATION_POLICY_JSON`;
  - backward-compatible generic webhook fallback.
- Added Telegram webhook smoke integration coverage:
  - promo discount redeem -> purchase/payment credit chain;
  - referral reward choice callback flow with duplicate replay.

## Not Implemented
- Dedicated admin UI/workflow for promo campaign operations (CLI is available).
- Refund-driven promo rollback (`PR_REVOKED`) automation.

## Risks
- Promo rate limiting behavior is transactional and tested in integration, but large-scale concurrent load behavior is still unprofiled.

## Decisions
- Failure attempts are persisted in separate short transactions to avoid rollback loss on redeem errors.
- Promo discount settlement remains anchored to purchase flow (`init -> precheckout -> successful_payment`) to preserve fixed-price semantics.
