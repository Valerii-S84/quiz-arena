class GameSessionError(Exception):
    pass


class EnergyInsufficientError(GameSessionError):
    pass


class DailyChallengeAlreadyPlayedError(GameSessionError):
    pass


class SessionNotFoundError(GameSessionError):
    pass


class InvalidAnswerOptionError(GameSessionError):
    pass


class TournamentSessionStopNotAllowedError(GameSessionError):
    pass


class FriendChallengeNotFoundError(GameSessionError):
    pass


class FriendChallengeAccessError(GameSessionError):
    pass


class FriendChallengeFullError(GameSessionError):
    pass


class FriendChallengeCompletedError(GameSessionError):
    pass


class FriendChallengeExpiredError(GameSessionError):
    pass


class FriendChallengePaymentRequiredError(GameSessionError):
    pass


class FriendChallengeLimitExceededError(GameSessionError):
    pass
