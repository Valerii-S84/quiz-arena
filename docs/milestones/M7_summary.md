# M7 Summary

## Implemented
- Added all premium products to catalog:
  - `PREMIUM_STARTER` (7d / 29⭐)
  - `PREMIUM_MONTH` (30d / 99⭐)
  - `PREMIUM_SEASON` (90d / 249⭐)
  - `PREMIUM_YEAR` (365d / 499⭐)
- Added premium entitlement application during successful payment credit.
- Implemented premium upgrade behavior:
  - new premium end = `max(current_end, now) + purchased_days`;
  - previous active premium entitlement is revoked on upgrade.
- Added downgrade guard: lower/equal premium tier purchase is blocked while higher tier is active.
- Added bot-side premium feedback messages and downgrade-blocked alert handling.

## Not Implemented
- Premium expiry push notifications and re-engagement offer routing.
- Premium+Mega interaction matrix for UX-specific upsell paths.

## Risks
- Premium purchase side effects rely on DB row locking and transactional ordering; high-contention behavior should be load-tested.
- Entitlement scope semantics for non-purchase grants (promo grants) are implemented but may still need product-level policy tuning.

## Decisions
- Reused purchase credit transaction as the single source of truth for premium entitlement mutation.
- Kept downgrade rejection at purchase init stage to fail fast before invoice send.
