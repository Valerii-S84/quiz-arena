# Promo Incident Response Runbook

## Scope

Use this runbook when promo behavior is degraded:
- campaign(s) auto-paused,
- abnormal redeem failures (`INVALID`, `NOT_APPLICABLE`, `RATE_LIMITED`),
- promo-linked payment reconciliation anomalies.

Primary related alert events:
- `promo_campaign_auto_paused`
- `payments_reconciliation_diff_detected` (promo-linked suspicion)

## Preconditions

```bash
ssh root@deutchquizarena.de
cd /opt/quiz-arena
source /opt/quiz-arena/.env
```

All SQL examples below are executed via production postgres container.

## 1) Immediate triage

### 1.1 Current promo status distribution

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select status, count(*) from promo_codes group by status order by status;"
```

### 1.2 Recently paused campaigns

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, campaign_name, code_prefix, status, updated_at \
 from promo_codes \
 where status = 'PAUSED' \
 order by updated_at desc \
 limit 50;"
```

### 1.3 Failed promo attempts (last 30 min)

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select normalized_code_hash, result, count(*) as attempts, max(attempted_at) as last_seen \
 from promo_attempts \
 where attempted_at >= now() - interval '30 minutes' \
 group by normalized_code_hash, result \
 order by attempts desc \
 limit 50;"
```

Expected:
- pause reason is explainable by traffic pattern,
- no uncontrolled spread across unrelated campaigns.

## 2) Incident classification

- `Abuse likely`:
  - large failed-attempt volume on same hash(es),
  - many distinct users/IP patterns,
  - recent auto-pause event.
- `False positive`:
  - known valid campaign paused with no real abuse pattern,
  - UX/input mistakes dominate failures.
- `Config regression`:
  - invalid campaign window (`valid_from/valid_until`),
  - wrong `target_scope`,
  - exhausted limits (`max_total_uses`, per-user constraints).

## 3) Containment

- If abuse is ongoing:
  - keep affected campaigns `PAUSED`,
  - prepare replacement batch/codes.
- If false positive:
  - validate campaign configuration,
  - unpause only specific clean campaign IDs.
- If config regression:
  - correct campaign parameters first,
  - unpause only after validation queries are clean.

## 4) Safe unpause procedure

### 4.1 Verify candidate campaign metadata

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select id, campaign_name, promo_type, target_scope, status, valid_from, valid_until, \
        max_total_uses, used_total \
 from promo_codes \
 where id = <promo_code_id>;"
```

### 4.2 Unpause one campaign

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"update promo_codes \
 set status = 'ACTIVE', updated_at = now() \
 where id = <promo_code_id> and status = 'PAUSED';"
```

### 4.3 Monitor for 10-15 minutes

- `promo_attempts` failure mix,
- successful redemptions (`promo_redemptions.status='APPLIED'`),
- repeated autopause alerts.

Expected:
- no rapid return to `PAUSED`,
- failure rate returns to normal baseline.

## 5) Post-incident validation

### 5.1 Validate recent redemption/payment consistency

```bash
docker compose -f docker-compose.prod.yml --env-file /opt/quiz-arena/.env exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off -c \
"select pr.id, pr.status, p.status as purchase_status, p.discount_stars_amount \
 from promo_redemptions pr \
 left join purchases p on p.id = pr.applied_purchase_id \
 where pr.created_at >= now() - interval '1 hour' \
 order by pr.created_at desc \
 limit 30;"
```

### 5.2 Validate runtime health

```bash
curl -sS https://deutchquizarena.de/api/health
```

Expected:
- promo redemption lifecycle is coherent (`RESERVED`/`APPLIED`/`EXPIRED` as expected),
- no new reconciliation anomalies tied to promo flow.

## 6) Communication template

Include:
- incident start/end timestamps (UTC),
- affected campaign IDs/count,
- estimated user impact,
- applied mitigation (`PAUSED`, unpaused IDs, rotated batch),
- follow-up checkpoint time.

## 7) Escalation

- Escalate to product owner if high-value campaign stays paused over 30 minutes.
- Escalate to backend on-call if auto-pause/unpause behavior deviates from guard logic.
