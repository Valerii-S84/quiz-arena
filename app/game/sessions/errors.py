class GameSessionError(Exception):
    pass


class EnergyInsufficientError(GameSessionError):
    pass


class ModeLockedError(GameSessionError):
    pass


class DailyChallengeAlreadyPlayedError(GameSessionError):
    pass


class SessionNotFoundError(GameSessionError):
    pass


class InvalidAnswerOptionError(GameSessionError):
    pass
