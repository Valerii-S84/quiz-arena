from __future__ import annotations


class SessionContextStub:
    def __init__(self, session: object, *, fail_on_commit: bool = False) -> None:
        self._session = session
        self._fail_on_commit = fail_on_commit

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None and self._fail_on_commit:
            raise RuntimeError("commit failed")
        return False


class SessionLocalStub:
    def __init__(self, *, fail_on_commit_calls: tuple[int, ...] = ()) -> None:
        self._call_count = 0
        self._fail_on_commit_calls = set(fail_on_commit_calls)

    def begin(self) -> SessionContextStub:
        self._call_count += 1
        return SessionContextStub(
            object(),
            fail_on_commit=self._call_count in self._fail_on_commit_calls,
        )


__all__ = ["SessionLocalStub"]
