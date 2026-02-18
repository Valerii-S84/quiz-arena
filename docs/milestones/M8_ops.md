# M8 Ops

## Added
- Offer trigger engine integrated into bot runtime:
  - `/start` surface,
  - locked-mode click branch,
  - energy-empty branch.
- Persistent impression audit trail in `offers_impressions` for shown offers.
- User-driven 72h offer mute via `offer:dismiss:<impression_id>` callback.
- Anti-spam runtime guards (6h modal, 3/day, 24h same-offer) enforced before rendering.

## Operational Notes
- Offer rendering now depends on DB write success for impression logging (intentional anti-spam safety).
- No extra workers/cron jobs added in M8.

## Missing for Next Milestones
- Push/offline offer delivery channel and cap tracking (`max 2/day`).
- Offer conversion instrumentation (`clicked_at` on CTA click, `converted_purchase_id` linkage).
- Offer funnel dashboards and alert thresholds (drop in conversion, spam anomalies).
