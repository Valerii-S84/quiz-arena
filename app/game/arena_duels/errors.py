from __future__ import annotations


class ArenaDuelError(Exception):
    pass


class ArenaDuelNotFoundError(ArenaDuelError):
    pass


class ArenaDuelAccessError(ArenaDuelError):
    pass


class ArenaDuelIncompleteError(ArenaDuelError):
    pass
