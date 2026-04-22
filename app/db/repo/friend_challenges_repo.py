from __future__ import annotations

from app.db.repo.friend_challenges_repo_core import FriendChallengesRepoCoreMixin
from app.db.repo.friend_challenges_repo_deadlines import FriendChallengesRepoDeadlineMixin


class FriendChallengesRepo(FriendChallengesRepoCoreMixin, FriendChallengesRepoDeadlineMixin):
    pass
