class TournamentError(Exception):
    pass


class TournamentNotFoundError(TournamentError):
    pass


class TournamentAccessError(TournamentError):
    pass


class TournamentClosedError(TournamentError):
    pass


class TournamentFullError(TournamentError):
    pass


class TournamentAlreadyStartedError(TournamentError):
    pass


class TournamentInsufficientParticipantsError(TournamentError):
    pass
