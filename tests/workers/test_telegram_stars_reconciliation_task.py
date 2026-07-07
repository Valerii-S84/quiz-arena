from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.telegram_stars import (
    TelegramStarsClientError,
    TelegramStarTransaction,
    TelegramStarTransactionsPage,
)
from app.workers.tasks import payments_reliability_async
from tests.purchase_service_test_helpers import purchase_model


class _SessionContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _SessionLocal:
    def __init__(self) -> None:
        self.session = object()

    def __call__(self) -> _SessionContext:
        return _SessionContext(self.session)


def _settings(*, enabled: bool, dry_run: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token="bot-token-secret",
        telegram_stars_reconciliation_enabled=enabled,
        telegram_stars_reconciliation_dry_run=dry_run,
        telegram_stars_auto_recovery_enabled=False,
    )


def _transaction(
    *,
    transaction_id: str = "charge-1",
    amount: int = 29,
    telegram_user_id: int = 270,
    incoming: bool = True,
) -> TelegramStarTransaction:
    partner: dict[str, object] = {
        "type": "user",
        "transaction_type": "invoice_payment",
        "user": {"id": telegram_user_id},
        "invoice_payload": "invoice-1",
    }
    return TelegramStarTransaction(
        transaction_id=transaction_id,
        amount=amount,
        transaction_date=datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc),
        source=partner if incoming else None,
        receiver=None if incoming else partner,
        raw_payload={"id": transaction_id, "invoice_payload": "invoice-1"},
    )


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        payments_reliability_async, "get_settings", lambda: _settings(enabled=False)
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result == {
        "status": "disabled",
        "dry_run": True,
        "auto_recovery_enabled": False,
        "transactions_examined": 0,
    }


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_refuses_non_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: _settings(enabled=True, dry_run=False),
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result == {
        "status": "dry_run_required",
        "dry_run": False,
        "auto_recovery_enabled": False,
        "transactions_examined": 0,
    }


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_dry_run_classifies_transactions(
    monkeypatch,
) -> None:
    monkeypatch.setattr(payments_reliability_async, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    logged: list[dict[str, object]] = []
    monkeypatch.setattr(
        payments_reliability_async.logger,
        "info",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(self, *, limit: int) -> TelegramStarTransactionsPage:
            assert limit == 100
            return TelegramStarTransactionsPage(
                transactions=[
                    _transaction(),
                    _transaction(transaction_id="charge-credited"),
                    _transaction(transaction_id="charge-missing", amount=99),
                    _transaction(transaction_id="charge-refund", incoming=False),
                ]
            )

    async def _candidate_rows(
        session: object,
        *,
        transaction_id: str,
        invoice_payload: str | None,
        telegram_user_id: int | None,
        transaction_date: datetime,
        match_window: timedelta,
        limit: int = 20,
    ):
        del session, invoice_payload, telegram_user_id, match_window, limit
        if transaction_id == "charge-missing":
            return []

        purchase = purchase_model(
            status="CREDITED" if transaction_id == "charge-credited" else "PRECHECKOUT_OK",
            stars_amount=29,
            invoice_payload=f"invoice-{transaction_id}",
        )
        purchase.created_at = transaction_date - timedelta(minutes=5)
        purchase.telegram_payment_charge_id = (
            transaction_id if transaction_id == "charge-credited" else None
        )
        return [(purchase, 270)]

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _candidate_rows,
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result["status"] == "dry_run_completed"
    assert result["transactions_examined"] == 4
    assert result["classification_counts"] == {
        "WOULD_RECOVER_EXACT_MATCH": 1,
        "ALREADY_CREDITED": 1,
        "NO_DB_PURCHASE": 1,
        "IGNORED_OUTGOING_OR_REFUND": 1,
    }
    assert result["high_severity_findings"] == 2
    assert result["medium_severity_findings"] == 0

    serialized_logs = repr(logged)
    assert "bot-token-secret" not in serialized_logs
    assert "invoice-1" not in serialized_logs
    assert "charge-1" not in serialized_logs


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_reports_sanitized_client_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(payments_reliability_async, "get_settings", lambda: _settings(enabled=True))

    class FailingStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(self, *, limit: int) -> TelegramStarTransactionsPage:
            del limit
            raise TelegramStarsClientError(
                "telegram_stars_request_failed",
                error_type="TimeoutError",
            )

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FailingStarsClient)

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result == {
        "status": "telegram_error",
        "dry_run": True,
        "auto_recovery_enabled": False,
        "transactions_examined": 0,
        "error_type": "TimeoutError",
    }
