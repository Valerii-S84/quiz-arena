# Referrals Fraud Review Runbook

## Scope

Manual review flow for suspicious referral activity via internal APIs.

## Preconditions

- `INTERNAL_API_TOKEN` available.
- Source IP is allowed by `INTERNAL_API_ALLOWLIST`.
- If behind proxy/LB, proxy CIDRs are configured in `INTERNAL_API_TRUSTED_PROXIES`.
- API is reachable.

Recommended shell setup:

```bash
export INTERNAL_API_BASE_URL="https://deutchquizarena.de"
export INTERNAL_API_TOKEN="<secret>"
```

## 1) Fetch queue and baseline

### 1.1 Fraud-focused review queue (last 72h)

```bash
curl -sS \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/review-queue?window_hours=72&status=REJECTED_FRAUD&limit=100"
```

### 1.2 Dashboard snapshot for context

```bash
curl -sS \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/dashboard?window_hours=24"
```

Expected:
- queue payload contains candidates with status/details,
- dashboard metrics are internally consistent with current alert context.

## 2) Apply review decisions

Endpoint:
- `POST /internal/referrals/{referral_id}/review`

Supported decisions:
- `CONFIRM_FRAUD`
- `REOPEN`
- `CANCEL`

Always pass `expected_current_status` to avoid race-condition transitions.

### 2.1 Reopen false positive

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/123/review" \
  -d '{
    "decision": "REOPEN",
    "reason": "false positive after manual verification",
    "expected_current_status": "REJECTED_FRAUD"
  }'
```

### 2.2 Confirm fraud

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/123/review" \
  -d '{
    "decision": "CONFIRM_FRAUD",
    "reason": "confirmed abuse pattern",
    "expected_current_status": "REJECTED_FRAUD"
  }'
```

### 2.3 Cancel case

```bash
curl -sS -X POST \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/123/review" \
  -d '{
    "decision": "CANCEL",
    "reason": "invalid referral chain",
    "expected_current_status": "STARTED"
  }'
```

Expected:
- HTTP `200`,
- response contains updated `referral.status`,
- `idempotent_replay=false` for actual state change.

## 3) Verify outcomes

### 3.1 Re-query review queue

```bash
curl -sS \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/review-queue?window_hours=72&status=REJECTED_FRAUD&limit=100"
```

### 3.2 Check referral notification events (optional)

```bash
curl -sS \
  -H "X-Internal-Token: ${INTERNAL_API_TOKEN}" \
  "${INTERNAL_API_BASE_URL}/internal/referrals/events?window_hours=168&limit=200"
```

Expected:
- case moved to expected segment/status,
- no contradictory transitions.

## 4) Tuning guidance

- If many valid users are flagged:
  - raise `REFERRALS_ALERT_MAX_*` thresholds conservatively.
- If abuse passes through:
  - lower thresholds stepwise and observe at least 24h.

## 5) Safety rules

- Do not manually mutate `REWARDED` cases via review endpoint.
- Always include explicit reason for auditability.
- Apply changes in small batches, then re-check queue and dashboard.
