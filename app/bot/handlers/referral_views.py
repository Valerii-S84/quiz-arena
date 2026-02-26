from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.bot.texts.de import TEXTS_DE
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.referrals.constants import REWARD_CODE_MEGA_PACK
from app.economy.referrals.service import ReferralClaimResult, ReferralOverview


def _format_berlin_time(at_utc: datetime) -> str:
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).strftime("%d.%m %H:%M")


def _build_visual_progress_lines(*, overview: ReferralOverview) -> list[str]:
    qualified_slots = min(overview.progress_target, overview.progress_qualified)
    lines = []
    for slot_index in range(1, overview.progress_target + 1):
        text_key = (
            "msg.referral.progress.line.qualified"
            if slot_index <= qualified_slots
            else "msg.referral.progress.line.pending"
        )
        lines.append(TEXTS_DE[text_key].format(index=slot_index))
    remaining = max(0, overview.progress_target - qualified_slots)
    if remaining > 0:
        lines.append(TEXTS_DE["msg.referral.progress.remaining"].format(remaining=remaining))
    return lines


def _build_overview_text(*, overview: ReferralOverview, invite_link: str | None) -> str:
    lines = [
        TEXTS_DE["msg.referral.invite"],
        TEXTS_DE["msg.referral.progress"].format(qualified=overview.progress_qualified),
    ]
    lines.extend(_build_visual_progress_lines(overview=overview))

    if invite_link:
        lines.append(TEXTS_DE["msg.referral.link"])
    else:
        lines.append(
            TEXTS_DE["msg.referral.link.fallback"].format(referral_code=overview.referral_code)
        )

    if overview.pending_rewards_total > 0:
        lines.append(
            TEXTS_DE["msg.referral.pending"].format(
                pending=overview.pending_rewards_total,
                claimable=overview.claimable_rewards,
            )
        )

    if overview.claimable_rewards > 0:
        lines.append(TEXTS_DE["msg.referral.reward.choice"])
    elif overview.next_reward_at_utc is not None:
        lines.append(
            TEXTS_DE["msg.referral.next_reward_at"].format(
                next_reward_at=_format_berlin_time(overview.next_reward_at_utc)
            )
        )
    elif overview.deferred_rewards > 0:
        lines.append(TEXTS_DE["msg.referral.reward.monthly_cap"])

    return "\n".join(lines)


def _build_claim_status_text(claim: ReferralClaimResult) -> str:
    if claim.status == "CLAIMED":
        if claim.reward_code == REWARD_CODE_MEGA_PACK:
            return TEXTS_DE["msg.referral.reward.claimed.megapack"]
        return TEXTS_DE["msg.referral.reward.claimed.premium"]
    if claim.status == "TOO_EARLY":
        return TEXTS_DE["msg.referral.reward.too_early"]
    if claim.status == "MONTHLY_CAP":
        return TEXTS_DE["msg.referral.reward.monthly_cap"]
    return TEXTS_DE["msg.referral.reward.unavailable"]
