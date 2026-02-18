# M6 Summary (Slice 1)

## Implemented
- Added purchase domain service (`PurchaseService`) with:
  - `init_purchase` (idempotent)
  - pre-checkout validation
  - successful payment credit application
- Added Telegram payment handlers:
  - `callback:buy:<product_code>` -> `send_invoice`
  - `pre_checkout_query` validation
  - `message.successful_payment` credit apply + success message
- Added product catalog for micro products:
  - `ENERGY_10`
  - `MEGA_PACK_15`
  - `STREAK_SAVER_20`
- Added purchase credit effects:
  - energy credit for `ENERGY_10` and `MEGA_PACK_15`
  - streak saver token credit for `STREAK_SAVER_20`
  - 24h mode access grants for Mega Pack modes with extension logic `max(current_end, now) + 24h`
- Connected payment router to dispatcher.

## Not Implemented
- FastAPI webhook endpoint and queue-based payment pipeline.
- Recovery/reconciliation jobs for `PAID_UNCREDITED`.
- Promo discount integration in purchase init.
- Premium product credit and entitlement upgrade/downgrade flow.

## Risks
- Flow is currently handler-driven (polling/webhook callback path), not yet decoupled into worker pipeline.
- Concurrency/idempotency for duplicated payment updates is covered logically but not proven in DB integration tests.

## Decisions
- Implemented M6 as direct Telegram-flow slice to validate invoice/pre-checkout/successful-payment chain end-to-end.
- Reused existing M3/M4 services for credit side effects to keep business logic centralized.
