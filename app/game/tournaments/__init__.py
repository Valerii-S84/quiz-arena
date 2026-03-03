from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.tournaments.service_facade import TournamentServiceFacade


def __getattr__(name: str) -> Any:
    if name == "TournamentServiceFacade":
        from app.game.tournaments.service_facade import TournamentServiceFacade

        return TournamentServiceFacade
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["TournamentServiceFacade"]
