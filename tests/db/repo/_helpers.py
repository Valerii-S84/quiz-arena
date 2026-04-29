from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.dialects import postgresql

from tests.type_helpers import AsyncSessionStub


class RecordingSession(AsyncSessionStub):
    def __init__(self, *results: object, get_result: object | None = None) -> None:
        self.added: list[object] = []
        self.added_all: list[object] = []
        self.flushed = False
        self.get_calls: list[tuple[object, object]] = []
        self.statement: object | None = None
        self.statements: list[object] = []
        self._results = list(results)
        self._get_result = get_result

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        *,
        execution_options: Any = None,
        bind_arguments: Any = None,
        _parent_execute_state: Any = None,
        _add_event: Any = None,
    ) -> Any:
        if not self._results:
            raise AssertionError("unexpected execute() call")
        self.statement = statement
        self.statements.append(statement)
        return self._results.pop(0)

    async def get(
        self,
        entity: Any,
        ident: Any,
        *,
        options: Any = None,
        populate_existing: bool = False,
        with_for_update: Any = None,
        identity_token: Any = None,
        execution_options: Any = None,
    ) -> Any | None:
        self.get_calls.append((entity, ident))
        return self._get_result

    def add(self, instance: object, _warn: bool = True) -> None:
        self.added.append(instance)

    def add_all(self, instances: Iterable[object]) -> None:
        self.added_all.extend(instances)

    async def flush(self, objects: Any = None) -> None:
        self.flushed = True


class IterableScalarsResult:
    def __init__(self, rows: Iterable[object]) -> None:
        self._rows = list(rows)

    def scalars(self) -> Iterable[object]:
        return iter(self._rows)


def compile_statement(statement: Any) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
