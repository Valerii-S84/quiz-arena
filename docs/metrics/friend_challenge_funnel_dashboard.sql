-- Friend Challenge Funnel / TTL Dashboard
-- Timezone: Europe/Berlin (stored field: local_date_berlin)

-- 1) Daily funnel counts (created -> joined -> completed -> rematch)
with daily as (
    select
        local_date_berlin,
        event_type,
        count(*) as total
    from analytics_events
    where event_type in (
        'friend_duel_created',
        'friend_duel_joined',
        'friend_duel_completed',
        'friend_duel_revanche_clicked'
    )
      and local_date_berlin >= (current_date - interval '30 day')
    group by local_date_berlin, event_type
)
select
    local_date_berlin,
    coalesce(max(total) filter (where event_type = 'friend_duel_created'), 0) as created_total,
    coalesce(max(total) filter (where event_type = 'friend_duel_joined'), 0) as joined_total,
    coalesce(max(total) filter (where event_type = 'friend_duel_completed'), 0) as completed_total,
    coalesce(max(total) filter (where event_type = 'friend_duel_revanche_clicked'), 0) as rematch_total
from daily
group by local_date_berlin
order by local_date_berlin desc;

-- 2) Daily conversion rates
with daily as (
    select
        local_date_berlin,
        count(*) filter (where event_type = 'friend_duel_created') as created_total,
        count(*) filter (where event_type = 'friend_duel_joined') as joined_total,
        count(*) filter (where event_type = 'friend_duel_completed') as completed_total,
        count(*) filter (where event_type = 'friend_duel_revanche_clicked') as rematch_total
    from analytics_events
    where event_type in (
        'friend_duel_created',
        'friend_duel_joined',
        'friend_duel_completed',
        'friend_duel_revanche_clicked'
    )
      and local_date_berlin >= (current_date - interval '30 day')
    group by local_date_berlin
)
select
    local_date_berlin,
    created_total,
    joined_total,
    completed_total,
    rematch_total,
    case when created_total > 0 then round(joined_total::numeric / created_total, 4) else 0 end as created_to_joined_rate,
    case when joined_total > 0 then round(completed_total::numeric / joined_total, 4) else 0 end as joined_to_completed_rate,
    case when completed_total > 0 then round(rematch_total::numeric / completed_total, 4) else 0 end as completed_to_rematch_rate
from daily
order by local_date_berlin desc;

-- 3) TTL outcomes for last 30 days (expired vs completed)
select
    local_date_berlin,
    count(*) filter (where event_type = 'friend_duel_completed') as completed_total,
    count(*) filter (where event_type = 'duel_expired') as expired_total,
    case
        when count(*) filter (where event_type in ('friend_duel_completed', 'duel_expired')) > 0
        then round(
            (count(*) filter (where event_type = 'duel_expired'))::numeric
            / (count(*) filter (where event_type in ('friend_duel_completed', 'duel_expired'))),
            4
        )
        else 0
    end as expired_share
from analytics_events
where event_type in ('friend_duel_completed', 'duel_expired')
  and local_date_berlin >= (current_date - interval '30 day')
group by local_date_berlin
order by local_date_berlin desc;

-- 4) Last chance notification delivery quality (worker)
select
    date_trunc('day', happened_at at time zone 'Europe/Berlin')::date as local_date_berlin,
    coalesce(sum((payload->>'sent_to')::int), 0) as sent_total,
    coalesce(sum((payload->>'failed_to')::int), 0) as failed_total,
    case
        when coalesce(sum((payload->>'sent_to')::int), 0) + coalesce(sum((payload->>'failed_to')::int), 0) > 0
        then round(
            coalesce(sum((payload->>'sent_to')::int), 0)::numeric
            / (coalesce(sum((payload->>'sent_to')::int), 0) + coalesce(sum((payload->>'failed_to')::int), 0)),
            4
        )
        else 0
    end as delivery_success_rate
from analytics_events
where event_type = 'friend_challenge_last_chance_sent'
  and happened_at >= (now() - interval '30 day')
group by 1
order by 1 desc;

-- 5) Proof Card share intent rate (clicked "Teilen" / completed duels)
with daily as (
    select
        local_date_berlin,
        count(*) filter (where event_type = 'friend_duel_completed') as completed_total,
        count(*) filter (where event_type = 'friend_duel_share_clicked') as share_clicked_total
    from analytics_events
    where event_type in (
        'friend_duel_completed',
        'friend_duel_share_clicked'
    )
      and local_date_berlin >= (current_date - interval '30 day')
    group by local_date_berlin
)
select
    local_date_berlin,
    completed_total,
    share_clicked_total,
    case
        when completed_total > 0
        then round(share_clicked_total::numeric / completed_total, 4)
        else 0
    end as proof_card_share_click_rate
from daily
order by local_date_berlin desc;
