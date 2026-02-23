from __future__ import annotations

from app.db.repo.promo_repo_attempts import (
    count_abusive_code_hashes,
    count_attempts_by_result,
    count_user_attempts,
    create_attempt,
    get_abusive_code_hashes,
    get_last_user_attempt_at,
)
from app.db.repo.promo_repo_codes import (
    count_campaigns_by_status,
    count_paused_campaigns_since,
    deplete_active_codes,
    expire_active_codes,
    get_code_by_hash,
    get_code_by_hash_for_update,
    get_code_by_id,
    get_code_by_id_for_update,
    list_codes,
    pause_active_codes_by_hashes,
)
from app.db.repo.promo_repo_redemptions import (
    count_discount_redemptions_by_status,
    count_redemptions_by_status,
    create_redemption,
    expire_reserved_redemptions,
    get_redemption_by_applied_purchase_id_for_update,
    get_redemption_by_code_and_user_for_update,
    get_redemption_by_id,
    get_redemption_by_id_for_update,
    get_redemption_by_idempotency_key,
    get_redemption_by_idempotency_key_for_update,
    get_refunded_purchase_ids_with_pending_redemption_revoke,
    revoke_redemption_for_refund,
)


class PromoRepo:
    get_code_by_hash = staticmethod(get_code_by_hash)
    get_code_by_hash_for_update = staticmethod(get_code_by_hash_for_update)
    get_code_by_id = staticmethod(get_code_by_id)
    get_code_by_id_for_update = staticmethod(get_code_by_id_for_update)
    list_codes = staticmethod(list_codes)

    get_redemption_by_id = staticmethod(get_redemption_by_id)
    get_redemption_by_id_for_update = staticmethod(get_redemption_by_id_for_update)
    get_redemption_by_applied_purchase_id_for_update = staticmethod(
        get_redemption_by_applied_purchase_id_for_update
    )
    revoke_redemption_for_refund = staticmethod(revoke_redemption_for_refund)
    get_refunded_purchase_ids_with_pending_redemption_revoke = staticmethod(
        get_refunded_purchase_ids_with_pending_redemption_revoke
    )
    get_redemption_by_idempotency_key = staticmethod(get_redemption_by_idempotency_key)
    get_redemption_by_idempotency_key_for_update = staticmethod(
        get_redemption_by_idempotency_key_for_update
    )
    get_redemption_by_code_and_user_for_update = staticmethod(
        get_redemption_by_code_and_user_for_update
    )
    create_redemption = staticmethod(create_redemption)

    create_attempt = staticmethod(create_attempt)
    count_user_attempts = staticmethod(count_user_attempts)
    count_attempts_by_result = staticmethod(count_attempts_by_result)
    get_last_user_attempt_at = staticmethod(get_last_user_attempt_at)

    expire_reserved_redemptions = staticmethod(expire_reserved_redemptions)
    expire_active_codes = staticmethod(expire_active_codes)
    deplete_active_codes = staticmethod(deplete_active_codes)

    count_redemptions_by_status = staticmethod(count_redemptions_by_status)
    count_discount_redemptions_by_status = staticmethod(count_discount_redemptions_by_status)
    count_campaigns_by_status = staticmethod(count_campaigns_by_status)
    count_paused_campaigns_since = staticmethod(count_paused_campaigns_since)

    get_abusive_code_hashes = staticmethod(get_abusive_code_hashes)
    count_abusive_code_hashes = staticmethod(count_abusive_code_hashes)
    pause_active_codes_by_hashes = staticmethod(pause_active_codes_by_hashes)
