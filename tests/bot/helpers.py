from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram import Bot as AiogramBot
    from aiogram.types import CallbackQuery as AiogramCallbackQuery
    from aiogram.types import Message as AiogramMessage


class DummySessionBegin:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class DummySessionLocal:
    def begin(self) -> DummySessionBegin:
        return DummySessionBegin()


@dataclass(slots=True)
class DummyAnswerCall:
    text: str | None
    kwargs: dict[str, Any]


if TYPE_CHECKING:

    class DummyBot(AiogramBot):
        username: str
        raise_on_get_me: bool
        raise_on_send_message: bool
        raise_on_send_photo: bool
        raise_on_send_invoice: bool
        sent_messages: list[dict[str, Any]]
        sent_photos: list[dict[str, Any]]
        sent_invoices: list[dict[str, Any]]

        def __init__(self, *, username: str = "quizarena_bot") -> None: ...

        async def get_me(self) -> SimpleNamespace: ...  # type: ignore[override]

        async def send_message(self, **kwargs: Any) -> None: ...  # type: ignore[override]

        async def send_photo(self, **kwargs: Any) -> None: ...  # type: ignore[override]

        async def send_invoice(self, **kwargs: Any) -> None: ...  # type: ignore[override]

    class DummyMessage(AiogramMessage):
        bot: DummyBot
        from_user: Any
        text: str | None
        message_id: int
        reply_to_message: Any
        successful_payment: Any
        answers: list[DummyAnswerCall]
        edit_reply_markup_calls: list[dict[str, Any]]

        def __init__(self, *, bot: DummyBot | None = None) -> None: ...

        async def answer(self, text: str | None = None, **kwargs: Any) -> None: ...  # type: ignore[override]

        async def answer_photo(  # type: ignore[override]
            self,
            photo: Any,
            caption: str | None = None,
            **kwargs: Any,
        ) -> None: ...

        async def edit_reply_markup(self, **kwargs: Any) -> None: ...  # type: ignore[override]

    class DummyCallback(AiogramCallbackQuery):
        data: str | None
        from_user: Any
        message: DummyMessage
        bot: DummyBot
        id: str
        answer_calls: list[dict[str, Any]]

        def __init__(
            self,
            *,
            data: str | None,
            from_user: SimpleNamespace | None,
            message: DummyMessage | None = None,
            callback_id: str = "cb-1",
        ) -> None: ...  # type: ignore[override]

        async def answer(  # type: ignore[override]
            self,
            text: str | None = None,
            show_alert: bool = False,
            **kwargs: Any,
        ) -> None: ...

else:

    class DummyBot:
        def __init__(self, *, username: str = "quizarena_bot") -> None:
            self.username = username
            self.raise_on_get_me = False
            self.raise_on_send_message = False
            self.raise_on_send_photo = False
            self.raise_on_send_invoice = False
            self.sent_messages: list[dict[str, Any]] = []
            self.sent_photos: list[dict[str, Any]] = []
            self.sent_invoices: list[dict[str, Any]] = []

        async def get_me(self) -> SimpleNamespace:
            if self.raise_on_get_me:
                raise RuntimeError("get_me failed")
            return SimpleNamespace(username=self.username)

        async def send_message(self, **kwargs: Any) -> None:
            if self.raise_on_send_message:
                raise RuntimeError("send_message failed")
            self.sent_messages.append(kwargs)

        async def send_photo(self, **kwargs: Any) -> None:
            if self.raise_on_send_photo:
                raise RuntimeError("send_photo failed")
            self.sent_photos.append(kwargs)

        async def send_invoice(self, **kwargs: Any) -> None:
            if self.raise_on_send_invoice:
                raise RuntimeError("send_invoice failed")
            self.sent_invoices.append(kwargs)

    class DummyMessage:
        def __init__(self, *, bot: DummyBot | None = None) -> None:
            self.bot = bot or DummyBot()
            self.answers: list[DummyAnswerCall] = []
            self.edit_reply_markup_calls: list[dict[str, Any]] = []

        async def answer(self, text: str | None = None, **kwargs: Any) -> None:
            self.answers.append(DummyAnswerCall(text=text, kwargs=kwargs))

        async def answer_photo(
            self,
            photo: Any,
            caption: str | None = None,
            **kwargs: Any,
        ) -> None:
            self.answers.append(
                DummyAnswerCall(
                    text=caption,
                    kwargs={
                        "photo": photo,
                        **kwargs,
                    },
                )
            )

        async def edit_reply_markup(self, **kwargs: Any) -> None:
            self.edit_reply_markup_calls.append(kwargs)

    class DummyCallback:
        def __init__(
            self,
            *,
            data: str | None,
            from_user: SimpleNamespace | None,
            message: DummyMessage | None = None,
            callback_id: str = "cb-1",
        ) -> None:
            self.data = data
            self.from_user = from_user
            self.message = message or DummyMessage()
            self.bot = self.message.bot
            self.id = callback_id
            self.answer_calls: list[dict[str, Any]] = []

        async def answer(
            self,
            text: str | None = None,
            show_alert: bool = False,
            **kwargs: Any,
        ) -> None:
            self.answer_calls.append({"text": text, "show_alert": show_alert, **kwargs})
