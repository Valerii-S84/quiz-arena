class PurchaseError(Exception):
    pass


class ProductNotFoundError(PurchaseError):
    pass


class PurchaseNotFoundError(PurchaseError):
    pass


class PurchasePrecheckoutValidationError(PurchaseError):
    pass
