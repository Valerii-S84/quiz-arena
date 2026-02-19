# Referrals Fraud Review Runbook

## Purpose
- Provide a repeatable manual-review flow for suspicious referral activity.
- Use internal APIs to inspect queue candidates and apply review decisions safely.

## Prerequisites
- Internal API token (`X-Internal-Token`).
- Source IP included in `INTERNAL_API_ALLOWLIST`.
- API service running and reachable.

## 1) Fetch review queue
- Default queue focuses on fraud-rejected referrals in last 72h.

```bash
curl -sS \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "http://localhost:8000/internal/referrals/review-queue?window_hours=72&status=REJECTED_FRAUD&limit=100"
```

- Optional status filters: `STARTED`, `QUALIFIED`, `REWARDED`, `REJECTED_FRAUD`, `CANCELED`, `DEFERRED_LIMIT`.

## 2) Apply review decision
- Endpoint: `POST /internal/referrals/{referral_id}/review`.
- Decisions:
  - `CONFIRM_FRAUD`: keeps/sets status to `REJECTED_FRAUD` and enforces minimum fraud score.
  - `REOPEN`: moves `REJECTED_FRAUD` or `CANCELED` back to `STARTED`.
  - `CANCEL`: moves `STARTED`/`REJECTED_FRAUD` to `CANCELED`.

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "http://localhost:8000/internal/referrals/123/review" \
  -d '{
    "decision": "REOPEN",
    "reason": "false positive after manual verification",
    "expected_current_status": "REJECTED_FRAUD"
  }'
```

## 3) Verify result
- Check response payload:
  - `referral.status` is expected target status.
  - `idempotent_replay=false` for a real state change.
- Re-run queue query to confirm the case moved out/in expected segment.

## 4) Tuning guidance
- If many valid users are marked as fraud:
  - increase thresholds (`REFERRALS_ALERT_MAX_*`) conservatively.
- If obvious abuse slips through:
  - lower thresholds stepwise and monitor for 24h before next change.

## Safety notes
- Always pass `expected_current_status` to avoid race-induced wrong transitions.
- Do not mutate `REWARDED` cases through manual review endpoints.
