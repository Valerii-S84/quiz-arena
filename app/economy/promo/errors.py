class PromoError(Exception):
    pass


class PromoUserNotFoundError(PromoError):
    pass


class PromoInvalidError(PromoError):
    pass


class PromoExpiredError(PromoError):
    pass


class PromoAlreadyUsedError(PromoError):
    pass


class PromoNotApplicableError(PromoError):
    pass


class PromoRateLimitedError(PromoError):
    pass


class PromoIdempotencyConflictError(PromoError):
    pass
