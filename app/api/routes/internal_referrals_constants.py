from __future__ import annotations

REFERRAL_REVIEW_STATUSES = {
    "STARTED",
    "QUALIFIED",
    "REWARDED",
    "REJECTED_FRAUD",
    "CANCELED",
    "DEFERRED_LIMIT",
}
REFERRAL_REVIEW_DECISIONS = {"CONFIRM_FRAUD", "REOPEN", "CANCEL"}
REFERRAL_NOTIFICATION_EVENT_TYPES = {
    "referral_reward_milestone_available",
    "referral_reward_granted",
}
