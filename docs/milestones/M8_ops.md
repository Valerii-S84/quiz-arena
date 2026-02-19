# M8 Ops

## Added
- Offer trigger engine integrated into bot runtime:
  - `/start` surface,
  - locked-mode click branch,
  - energy-empty branch.
- Persistent impression audit trail in `offers_impressions` for shown offers.
- User-driven 72h offer mute via `offer:dismiss:<impression_id>` callback.
- Anti-spam runtime guards (6h modal, 3/day, 24h same-offer) enforced before rendering.
- Offer CTA attribution in payment flow:
  - `buy:<product>:offer:<impression_id>` callbacks,
  - `clicked_at` + `converted_purchase_id` updates in `offers_impressions`.
- New internal dashboard endpoint:
  - `GET /internal/offers/dashboard` with funnel metrics and threshold state.
- New periodic monitor:
  - `run_offers_funnel_alerts` every 15 minutes;
  - ops alerts on conversion drop and spam anomalies.

## Operational Notes
- Offer rendering now depends on DB write success for impression logging (intentional anti-spam safety).
- Offer monitoring thresholds are configurable via env:
  - `OFFERS_ALERT_WINDOW_HOURS`,
  - `OFFERS_ALERT_MIN_IMPRESSIONS`,
  - `OFFERS_ALERT_MIN_CONVERSION_RATE`,
  - `OFFERS_ALERT_MAX_DISMISS_RATE`,
  - `OFFERS_ALERT_MAX_IMPRESSIONS_PER_USER`.

## Missing for Next Milestones
- Push/offline offer delivery channel and cap tracking (`max 2/day`).
