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
  - German success/error texts for promo outcomes.

## Not Implemented
- Promo code batch generation/import tooling (admin path).
- Provider-specific alert routing templates (PagerDuty/Slack formatting, escalation policy bindings).
- Refund-driven promo rollback (`PR_REVOKED`) automation.

## Risks
- Promo rate limiting behavior is transactional and tested in integration, but large-scale concurrent load behavior is still unprofiled.

## Decisions
- Failure attempts are persisted in separate short transactions to avoid rollback loss on redeem errors.
- Promo discount settlement remains anchored to purchase flow (`init -> precheckout -> successful_payment`) to preserve fixed-price semantics.
