from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import payment_update_evidence


class _SessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def begin(self) -> _SessionContext:
        return _SessionContext()


def _successful_payment_update() -> dict[str, object]:
    return {
        "update_id": 777,
        "message": {
            "message_id": 1,
            "from": {"id": 270},
            "successful_payment": {
                "currency": "XTR",
                "total_amount": 29,
                "invoice_payload": "invoice-1",
                "telegram_payment_charge_id": "raw-telegram-charge",
                "provider_payment_charge_id": "raw-provider-charge",
                "order_info": {
                    "email": "buyer@example.com",
                    "phone_number": "+49123456789",
                    "shipping_address": {
                        "country_code": "DE",
                        "city": "Berlin",
                        "street_line1": "Private Strasse 1",
                    },
                },
            },
        },
    }


def test_sanitized_payment_update_evidence_excludes_raw_payment_payload() -> None:
    evidence = payment_update_evidence.sanitized_payment_update_evidence(
        update_payload=_successful_payment_update(),
        update_id=777,
        payment_update_kind="message.successful_payment",
    )

    assert evidence["payment_update_kind"] == "message.successful_payment"
    assert evidence["payment_update_key"] == "telegram:777:message.successful_payment"
    assert evidence["invoice_payload"] == "invoice-1"
    assert evidence["currency"] == "XTR"
    assert evidence["total_amount"] == 29
    assert evidence["telegram_user_id"] == 270
    assert evidence["message_id"] == 1
    assert evidence["order_info_present"] is True
    assert evidence["raw_payload_stored"] is False
    assert "raw_update" not in evidence
    assert "successful_payment" not in evidence
    assert "telegram_payment_charge_id" not in evidence
    assert "provider_payment_charge_id" not in evidence
    assert evidence["telegram_payment_charge_id_hash"] != "raw-telegram-charge"
    assert evidence["provider_payment_charge_id_hash"] != "raw-provider-charge"

    serialized = repr(evidence)
    assert "buyer@example.com" not in serialized
    assert "+49123456789" not in serialized
    assert "Private Strasse 1" not in serialized
    assert "raw-telegram-charge" not in serialized
    assert "raw-provider-charge" not in serialized


@pytest.mark.asyncio
async def test_store_payment_update_evidence_writes_inbox_then_payment_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _create_inbox(_session, **kwargs):
        calls.append(("inbox", kwargs))
        return SimpleNamespace(update_id=kwargs["update_id"]), True

    async def _create_event(_session, **kwargs):
        calls.append(("event", kwargs))
        return object(), True

    monkeypatch.setattr(payment_update_evidence, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        payment_update_evidence.TelegramUpdateInboxRepo,
        "create_once",
        _create_inbox,
    )
    monkeypatch.setattr(payment_update_evidence.PaymentEventsRepo, "create_once", _create_event)

    assert (
        await payment_update_evidence.store_payment_update_evidence(
            update_payload=_successful_payment_update(),
            update_id=777,
        )
        is True
    )

    assert [name for name, _ in calls] == ["inbox", "event"]
    inbox_payload = calls[0][1]["sanitized_evidence"]
    event_payload = calls[1][1]
    assert isinstance(inbox_payload, dict)
    assert event_payload["event_type"] == "SUCCESSFUL_PAYMENT"
    assert event_payload["idempotency_key"] == "telegram:777:message.successful_payment"
    assert event_payload["source_inbox_update_id"] == 777
    assert event_payload["provider_charge_id_hash"] != "raw-telegram-charge"
    assert event_payload["provider_payment_charge_id_hash"] != "raw-provider-charge"
    assert event_payload["safe_payload"] == inbox_payload
    assert "raw-telegram-charge" not in repr(calls)
    assert "buyer@example.com" not in repr(calls)


@pytest.mark.asyncio
async def test_store_payment_update_evidence_skips_non_payment_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingSessionLocal:
        def begin(self):
            raise AssertionError("non-payment updates must not open payment evidence session")

    monkeypatch.setattr(payment_update_evidence, "SessionLocal", _FailingSessionLocal())

    assert (
        await payment_update_evidence.store_payment_update_evidence(
            update_payload={"update_id": 1, "message": {"text": "/start"}},
            update_id=1,
        )
        is True
    )


@pytest.mark.asyncio
async def test_store_payment_update_evidence_returns_false_on_durable_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_inbox(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(payment_update_evidence, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        payment_update_evidence.TelegramUpdateInboxRepo,
        "create_once",
        _fail_inbox,
    )

    assert (
        await payment_update_evidence.store_payment_update_evidence(
            update_payload={"update_id": 778, "pre_checkout_query": {"id": "pre-1"}},
            update_id=778,
        )
        is False
    )
