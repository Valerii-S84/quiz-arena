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
        'friend_challenge_created',
        'friend_challenge_joined',
        'friend_challenge_completed',
        'friend_challenge_rematch_created'
    )
      and local_date_berlin >= (current_date - interval '30 day')
    group by local_date_berlin, event_type
)
select
    local_date_berlin,
    coalesce(max(total) filter (where event_type = 'friend_challenge_created'), 0) as created_total,
    coalesce(max(total) filter (where event_type = 'friend_challenge_joined'), 0) as joined_total,
    coalesce(max(total) filter (where event_type = 'friend_challenge_completed'), 0) as completed_total,
    coalesce(max(total) filter (where event_type = 'friend_challenge_rematch_created'), 0) as rematch_total
from daily
group by local_date_berlin
order by local_date_berlin desc;

-- 2) Daily conversion rates
with daily as (
    select
        local_date_berlin,
        count(*) filter (where event_type = 'friend_challenge_created') as created_total,
        count(*) filter (where event_type = 'friend_challenge_joined') as joined_total,
        count(*) filter (where event_type = 'friend_challenge_completed') as completed_total,
        count(*) filter (where event_type = 'friend_challenge_rematch_created') as rematch_total
    from analytics_events
    where event_type in (
        'friend_challenge_created',
        'friend_challenge_joined',
        'friend_challenge_completed',
        'friend_challenge_rematch_created'
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
    count(*) filter (where event_type = 'friend_challenge_completed') as completed_total,
    count(*) filter (where event_type = 'friend_challenge_expired') as expired_total,
    case
        when count(*) filter (where event_type in ('friend_challenge_completed', 'friend_challenge_expired')) > 0
        then round(
            (count(*) filter (where event_type = 'friend_challenge_expired'))::numeric
            / (count(*) filter (where event_type in ('friend_challenge_completed', 'friend_challenge_expired'))),
            4
        )
        else 0
    end as expired_share
from analytics_events
where event_type in ('friend_challenge_completed', 'friend_challenge_expired')
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
