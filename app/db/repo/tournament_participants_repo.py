from __future__ import annotations

from app.db.repo.tournament_participants_repo_queries import TournamentParticipantsRepoQueriesMixin
from app.db.repo.tournament_participants_repo_updates import TournamentParticipantsRepoUpdatesMixin


class TournamentParticipantsRepo(
    TournamentParticipantsRepoQueriesMixin,
    TournamentParticipantsRepoUpdatesMixin,
):
    pass
