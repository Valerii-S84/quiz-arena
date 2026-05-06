from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.economy.energy import EnergyService
    from app.economy.offers import OfferService
    from app.economy.promo import PromoService
    from app.economy.purchases import PurchaseService
    from app.economy.referrals import ReferralService
    from app.economy.streak import StreakService


def __getattr__(name: str) -> Any:
    if name == "EnergyService":
        from app.economy.energy import EnergyService

        return EnergyService
    if name == "OfferService":
        from app.economy.offers import OfferService

        return OfferService
    if name == "PromoService":
        from app.economy.promo import PromoService

        return PromoService
    if name == "PurchaseService":
        from app.economy.purchases import PurchaseService

        return PurchaseService
    if name == "ReferralService":
        from app.economy.referrals import ReferralService

        return ReferralService
    if name == "StreakService":
        from app.economy.streak import StreakService

        return StreakService
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "EnergyService",
    "OfferService",
    "PromoService",
    "PurchaseService",
    "ReferralService",
    "StreakService",
]
