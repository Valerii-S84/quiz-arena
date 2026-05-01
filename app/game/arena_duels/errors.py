from __future__ import annotations


class ArenaDuelError(Exception):
    pass


class ArenaDuelNotFoundError(ArenaDuelError):
    pass


class ArenaDuelAccessError(ArenaDuelError):
    pass


class ArenaDuelAlreadyAttemptedError(ArenaDuelAccessError):
    pass


class ArenaDuelExpiredError(ArenaDuelAccessError):
    pass


class ArenaDuelOwnAttemptError(ArenaDuelAccessError):
    pass


class ArenaDuelIncompleteError(ArenaDuelError):
    pass
