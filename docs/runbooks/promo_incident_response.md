# Promo Incident Response Runbook

## Scope
Use this runbook when promo campaigns are auto-paused, over-restricted, or producing abnormal error rates.

Primary trigger events:
- `promo_campaign_auto_paused`;
- `payments_reconciliation_diff_detected` where promo-linked purchases are suspected;
- sustained promo redeem failures (`INVALID`/`NOT_APPLICABLE`/`RATE_LIMITED`) above baseline.

## 1) Immediate triage
1. Confirm current blast radius:
```sql
select status, count(*)
from promo_codes
group by status
order by status;
```
2. List newly paused campaigns:
```sql
select id, campaign_name, code_prefix, status, updated_at
from promo_codes
where status = 'PAUSED'
order by updated_at desc
limit 50;
```
3. Inspect recent failed attempts by hash:
```sql
select normalized_code_hash, result, count(*) as attempts, max(attempted_at) as last_seen
from promo_attempts
where attempted_at >= now() - interval '30 minutes'
group by normalized_code_hash, result
order by attempts desc
limit 50;
```

## 2) Classify incident
- `Abuse likely`: high invalid attempts across many users, repeated hash abuse patterns.
- `False positive`: known campaign hash paused but failure cluster tied to UX/typing issues.
- `Config regression`: code validity window, target scope, or limits misconfigured.

## 3) Containment actions
- If abuse is ongoing:
  - keep impacted campaigns `PAUSED`;
  - rotate/replace leaked campaign batch.
- If false positive:
  - validate campaign config and recent traffic source;
  - unpause only confirmed clean campaign IDs.
- If config regression:
  - fix campaign fields (`valid_until`, `target_scope`, limits) before unpause.

## 4) Safe unpause procedure
1. Verify campaign metadata:
```sql
select id, campaign_name, promo_type, target_scope, status, valid_from, valid_until, max_total_uses, used_total
from promo_codes
where id = <promo_code_id>;
```
2. Ensure abuse burst is no longer active (repeat triage query from section 1).
3. Unpause single campaign:
```sql
update promo_codes
set status = 'ACTIVE', updated_at = now()
where id = <promo_code_id>
  and status = 'PAUSED';
```
4. Monitor for 10-15 minutes:
  - `promo_attempts` failure mix;
  - redemption success count;
  - repeat autopause alerts.

## 5) Post-incident validation
1. Redeem one controlled test code in staging/sandbox.
2. Validate purchase settlement for discount campaigns:
```sql
select pr.id, pr.status, p.status as purchase_status, p.discount_stars_amount
from promo_redemptions pr
left join purchases p on p.id = pr.applied_purchase_id
where pr.created_at >= now() - interval '1 hour'
order by pr.created_at desc
limit 30;
```
3. Confirm no reconciliation drift for recent window.

## 6) Communication template
- Incident start timestamp (UTC).
- Affected campaigns/count.
- User impact estimate.
- Action taken (`PAUSED`, unpaused IDs, batch rotated).
- Next checkpoint time.

## 7) Escalation
- Escalate to product owner if active high-value campaign must remain paused > 30 minutes.
- Escalate to backend on-call if pause/unpause behavior deviates from guard logic.
