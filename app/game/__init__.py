from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.sessions.service import GameSessionService
    from app.game.tournaments import TournamentServiceFacade


def __getattr__(name: str) -> Any:
    if name == "GameSessionService":
        from app.game.sessions.service import GameSessionService

        return GameSessionService
    if name == "TournamentServiceFacade":
        from app.game.tournaments import TournamentServiceFacade

        return TournamentServiceFacade
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["GameSessionService", "TournamentServiceFacade"]
