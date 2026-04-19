from __future__ import annotations

from app.db.repo.friend_challenges_repo_access import (
    create,
    get_by_id,
    get_by_id_for_update,
    get_by_invite_token,
    get_by_invite_token_for_update,
    list_by_series_id_for_update,
    list_recent_for_user,
)
from app.db.repo.friend_challenges_repo_metrics import (
    count_by_creator_access_type,
    count_created_since,
    count_live_for_user,
    count_live_open_by_creator,
    list_active_due_for_expire_for_update,
    list_active_due_for_last_chance_for_update,
    list_joined_due_for_walkover_for_update,
    list_pending_due_for_expire_for_update,
)


class FriendChallengesRepo:
    get_by_id = staticmethod(get_by_id)
    get_by_id_for_update = staticmethod(get_by_id_for_update)
    get_by_invite_token = staticmethod(get_by_invite_token)
    get_by_invite_token_for_update = staticmethod(get_by_invite_token_for_update)
    create = staticmethod(create)
    count_by_creator_access_type = staticmethod(count_by_creator_access_type)
    count_live_for_user = staticmethod(count_live_for_user)
    count_live_open_by_creator = staticmethod(count_live_open_by_creator)
    count_created_since = staticmethod(count_created_since)
    list_recent_for_user = staticmethod(list_recent_for_user)
    list_active_due_for_last_chance_for_update = staticmethod(
        list_active_due_for_last_chance_for_update
    )
    list_active_due_for_expire_for_update = staticmethod(list_active_due_for_expire_for_update)
    list_pending_due_for_expire_for_update = staticmethod(list_pending_due_for_expire_for_update)
    list_joined_due_for_walkover_for_update = staticmethod(list_joined_due_for_walkover_for_update)
    list_by_series_id_for_update = staticmethod(list_by_series_id_for_update)
