class PurchaseError(Exception):
    pass


class ProductNotFoundError(PurchaseError):
    pass


class PurchaseNotFoundError(PurchaseError):
    pass


class PurchasePrecheckoutValidationError(PurchaseError):
    pass


class PurchaseInitValidationError(PurchaseError):
    pass


class PurchaseRefundValidationError(PurchaseError):
    pass


class PurchaseRefundInvariantError(PurchaseError):
    pass


class PremiumDowngradeNotAllowedError(PurchaseInitValidationError):
    pass


class StreakSaverPurchaseLimitError(PurchaseInitValidationError):
    pass
