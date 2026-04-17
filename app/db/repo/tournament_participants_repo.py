from __future__ import annotations

from .tournament_participants_repo_queries import TournamentParticipantsRepoQueriesMixin
from .tournament_participants_repo_updates import TournamentParticipantsRepoUpdatesMixin


class TournamentParticipantsRepo(
    TournamentParticipantsRepoQueriesMixin,
    TournamentParticipantsRepoUpdatesMixin,
):
    pass
