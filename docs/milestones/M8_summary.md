# M8 Summary

## Implemented
- Added Offer Trigger Engine (`app/economy/offers/service.py`) with full M8 trigger matrix evaluation:
  - `TRG_ENERGY_ZERO`, `TRG_ENERGY_LOW`, `TRG_ENERGY10_SECOND_BUY`,
  - `TRG_LOCKED_MODE_CLICK`, `TRG_STREAK_GT7`, `TRG_STREAK_RISK_22`,
  - `TRG_STREAK_MILESTONE_30`, `TRG_COMEBACK_3D`, `TRG_MEGA_THIRD_BUY`,
  - `TRG_STARTER_EXPIRED`, `TRG_MONTH_EXPIRING`, `TRG_WEEKEND_FLASH`.
- Added deterministic priority resolver aligned to spec conflict order.
- Added anti-spam controls:
  - max 1 blocking offer / 6h;
  - max 3 monetization impressions / Berlin day;
  - same `offer_code` max once / 24h;
  - per-offer mute for 72h after `Nicht zeigen`.
- Added idempotent offer impression logging on `offers_impressions` (`idempotency_key` conflict-safe insert).
- Added offer dismiss flow:
  - callback `offer:dismiss:<impression_id>`;
  - persists `dismiss_reason=NOT_SHOW` and mute timestamp.
- Added bot integration points:
  - `/start` evaluates and shows best eligible offer;
  - locked mode click path evaluates offers (including energy-zero override);
  - empty-energy path evaluates offers with caps.
- Added offer UI layer:
  - offer CTA keyboard builder with product buy actions;
  - German offer copy keys added to `TEXTS_DE`.
- Added DB repo support:
  - `OffersRepo` for impression history/logging/dismiss;
  - purchase history window count methods for trigger conditions;
  - entitlement window checks for starter-expired and month-expiring triggers.

## Not Implemented
- Push-notification offer channel and push cap enforcement (`max 2/day`) are not implemented in this slice.
- Offer click-through and purchase conversion attribution (`clicked_at` from CTA click, `converted_purchase_id`) is not yet wired to purchase flow.
- Dedicated analytics/dashboard/reporting for offer funnel is not implemented.

## Risks
- Trigger evaluation currently executes several DB reads per check; high-throughput optimization (pre-aggregates/caching) may be needed under load.
- Dismiss timestamp is stored in `clicked_at` for now (schema reuse); analytics semantics should be split later if precise click tracking is required.

## Decisions
- Kept offer impression logging strictly idempotent and conflict-safe using DB `ON CONFLICT DO NOTHING`, then replay lookup.
- Enforced "log first, then show" semantics: if logging cannot be resolved, offer is not shown.
- Integrated offers only at high-intent surfaces (`/start`, locked-mode click, energy-empty) to avoid unsolicited spam before push infrastructure exists.
