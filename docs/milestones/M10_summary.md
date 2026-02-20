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
- Added external Telegram sandbox runbook:
  - `docs/runbooks/telegram_sandbox_stars_smoke.md`.
- Added promo incident response runbook:
  - `docs/runbooks/promo_incident_response.md`.
- Added internal promo admin operations workflow (API-first):
  - `GET /internal/promo/campaigns` for filtered campaign listing;
  - `POST /internal/promo/campaigns/{promo_code_id}/status` for safe status transitions;
  - `POST /internal/promo/refund-rollback` for manual refund rollback with idempotent replay behavior.
- Added safe campaign transition guardrails:
  - only `ACTIVE <-> PAUSED` transitions are mutable from admin API;
  - reactivating `DEPLETED/EXPIRED` campaigns through this endpoint is rejected.
- Added refund-driven promo rollback automation (`PR_REVOKED` flow):
  - periodic worker `run_refund_promo_rollback` finds `REFUNDED` purchases with non-revoked promo redemptions;
  - marks `promo_redemptions.status='REVOKED'` idempotently.

## Not Implemented
- No unresolved functional gaps in M10 scope at this moment.

## Risks
- Promo rate limiting behavior is transactional and tested in integration, but large-scale concurrent load behavior is still unprofiled.

## Decisions
- Failure attempts are persisted in separate short transactions to avoid rollback loss on redeem errors.
- Promo discount settlement remains anchored to purchase flow (`init -> precheckout -> successful_payment`) to preserve fixed-price semantics.
- On refund rollback, `promo_codes.used_total` is intentionally not decremented (audit-conservative accounting model from spec).
