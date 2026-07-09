from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest

from app.services.telegram_stars import (
    TelegramStarsClient,
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

    def begin(self) -> _SessionContext:
        return _SessionContext(self.session)


def _settings(
    *,
    enabled: bool,
    dry_run: bool = True,
    auto_recovery_enabled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token="bot-token-secret",
        telegram_stars_reconciliation_enabled=enabled,
        telegram_stars_reconciliation_dry_run=dry_run,
        telegram_stars_auto_recovery_enabled=auto_recovery_enabled,
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
async def test_fetch_star_transactions_backlog_pages_until_short_page() -> None:
    calls: list[tuple[int, int]] = []
    first_page = [
        _transaction(transaction_id=f"charge-page-1-{index}", incoming=False)
        for index in range(100)
    ]
    second_page = [_transaction(transaction_id="charge-page-2", incoming=False)]

    class FakeStarsClient:
        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            calls.append((offset, limit))
            if offset == 0:
                return TelegramStarTransactionsPage(transactions=first_page)
            if offset == 100:
                return TelegramStarTransactionsPage(transactions=second_page)
            return TelegramStarTransactionsPage(transactions=[])

    transactions, pages_fetched = await payments_reliability_async._fetch_star_transactions_backlog(
        cast(TelegramStarsClient, FakeStarsClient())
    )

    assert calls == [(0, 100), (100, 100)]
    assert transactions == [*first_page, *second_page]
    assert pages_fetched == 2


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
        "status": "auto_recovery_disabled",
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
    review_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        payments_reliability_async.logger,
        "info",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            assert offset == 0
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
        for_update: bool = False,
    ):
        del session, invoice_payload, telegram_user_id, match_window, limit, for_update
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

    async def _create_review_once(
        session: object,
        *,
        event_type: str,
        payload: dict[str, object],
        payload_key: str,
        status: str,
    ):
        del session
        assert event_type == "payments_telegram_stars_reconciliation_review"
        assert payload_key == "review_key"
        assert status == "OPEN"
        review_payloads.append(payload)
        return object(), True

    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
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
    assert result["review_findings"] == 2
    assert result["review_events_created"] == 2
    assert result["review_events_existing"] == 0

    assert [payload["reason"] for payload in review_payloads] == [
        "WOULD_RECOVER_EXACT_MATCH",
        "NO_DB_PURCHASE",
    ]
    serialized_reviews = repr(review_payloads)
    assert "bot-token-secret" not in serialized_reviews
    assert "invoice-1" not in serialized_reviews
    assert "charge-1" not in serialized_reviews
    assert all(payload["raw_payload_stored"] is False for payload in review_payloads)

    serialized_logs = repr(logged)
    assert "bot-token-secret" not in serialized_logs
    assert "invoice-1" not in serialized_logs
    assert "charge-1" not in serialized_logs


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_deduplicates_open_review_events(
    monkeypatch,
) -> None:
    monkeypatch.setattr(payments_reliability_async, "get_settings", lambda: _settings(enabled=True))
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    seen_review_keys: set[str] = set()

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
            return TelegramStarTransactionsPage(transactions=[_transaction()])

    async def _no_candidate_rows(*_args, **_kwargs):
        return []

    async def _create_review_once(
        session: object,
        *,
        event_type: str,
        payload: dict[str, object],
        payload_key: str,
        status: str,
    ):
        del session, event_type, payload_key, status
        review_key = str(payload["review_key"])
        if review_key in seen_review_keys:
            return object(), False
        seen_review_keys.add(review_key)
        return object(), True

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _no_candidate_rows,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
    )

    first = await payments_reliability_async.run_telegram_stars_reconciliation_async()
    second = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert first["review_events_created"] == 1
    assert first["review_events_existing"] == 0
    assert second["review_events_created"] == 0
    assert second["review_events_existing"] == 1


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_auto_recovers_exact_match_once(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: _settings(enabled=True, dry_run=False, auto_recovery_enabled=True),
    )
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    purchase = purchase_model(
        status="PRECHECKOUT_OK",
        stars_amount=29,
        invoice_payload="invoice-1",
        product_code="PREMIUM_WEEK",
        product_type="PREMIUM",
    )
    purchase.created_at = datetime(2026, 7, 7, 11, 55, tzinfo=timezone.utc)
    recovery_now_utc = datetime(2026, 7, 9, 9, 15, tzinfo=timezone.utc)
    apply_calls: list[dict[str, object]] = []
    outbox_events: list[dict[str, object]] = []

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
            return TelegramStarTransactionsPage(transactions=[_transaction()])

    async def _candidate_rows(*_args, **_kwargs):
        return [(purchase, 270)]

    async def _get_purchase_for_update(_session, purchase_id):
        assert purchase_id == purchase.id
        return purchase

    async def _get_charge_purchase(_session, telegram_payment_charge_id: str):
        if purchase.telegram_payment_charge_id == telegram_payment_charge_id:
            return purchase
        return None

    async def _no_ledger(_session, *, purchase_id):
        assert purchase_id == purchase.id
        return None

    async def _no_entitlement(_session, *, purchase_id, entitlement_type: str):
        assert purchase_id == purchase.id
        assert entitlement_type == "PREMIUM"
        return None

    async def _no_open_review(*_args, **_kwargs):
        return None

    async def _apply_successful_payment(
        _session,
        *,
        user_id: int,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        raw_successful_payment: dict[str, object],
        now_utc: datetime,
    ):
        apply_calls.append(
            {
                "user_id": user_id,
                "invoice_payload": invoice_payload,
                "telegram_payment_charge_id": telegram_payment_charge_id,
                "raw_successful_payment": raw_successful_payment,
                "now_utc": now_utc,
            }
        )
        purchase.status = "CREDITED"
        purchase.telegram_payment_charge_id = telegram_payment_charge_id
        return SimpleNamespace(status="CREDITED", idempotent_replay=False)

    async def _create_outbox(_session, *, event_type: str, payload: dict[str, object], status: str):
        outbox_events.append({"event_type": event_type, "payload": payload, "status": status})
        return object()

    async def _create_review_once(*_args, **_kwargs):
        raise AssertionError("exact auto-recovery success must not create a review event")

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _candidate_rows,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_id_for_update",
        _get_purchase_for_update,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "get_by_telegram_payment_charge_id_for_update",
        _get_charge_purchase,
    )
    monkeypatch.setattr(
        payments_reliability_async.LedgerRepo,
        "get_purchase_credit_for_update",
        _no_ledger,
    )
    monkeypatch.setattr(
        payments_reliability_async.EntitlementsRepo,
        "get_by_source_purchase_id_for_update",
        _no_entitlement,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "get_open_by_payload_key",
        _no_open_review,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
    )
    monkeypatch.setattr(payments_reliability_async.OutboxEventsRepo, "create", _create_outbox)
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )
    monkeypatch.setattr(payments_reliability_async, "_now_utc", lambda: recovery_now_utc)

    first = await payments_reliability_async.run_telegram_stars_reconciliation_async()
    second = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert first["status"] == "auto_recovery_completed"
    assert first["auto_recovered"] == 1
    assert first["auto_recovery_counts"] == {"auto_recovered": 1}
    assert first["review_findings"] == 0
    assert second["auto_recovery_counts"] == {"already_credited": 1}
    assert len(apply_calls) == 1
    assert apply_calls[0]["invoice_payload"] == "invoice-1"
    assert apply_calls[0]["telegram_payment_charge_id"] == "charge-1"
    assert apply_calls[0]["now_utc"] == recovery_now_utc
    raw_successful_payment = apply_calls[0]["raw_successful_payment"]
    assert isinstance(raw_successful_payment, dict)
    assert raw_successful_payment["currency"] == "XTR"
    assert raw_successful_payment["total_amount"] == 29
    assert raw_successful_payment["transaction_date"] == "2026-07-07T12:00:00+00:00"
    assert len(outbox_events) == 1
    assert outbox_events[0]["event_type"] == "payments_telegram_star_auto_recovered"
    assert outbox_events[0]["status"] == "SENT"
    payload = outbox_events[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["schema_version"] == 1
    assert payload["source"] == "telegram_stars_reconciliation"
    assert payload["purchase_id"] == str(purchase.id)
    assert payload["classification"] == "WOULD_RECOVER_EXACT_MATCH"
    assert isinstance(payload["transaction_id_hash"], str)
    serialized_outbox = repr(outbox_events)
    assert "bot-token-secret" not in serialized_outbox
    assert "invoice-1" not in serialized_outbox
    assert "charge-1" not in serialized_outbox


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_auto_mode_reviews_ambiguous_match(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: _settings(enabled=True, dry_run=False, auto_recovery_enabled=True),
    )
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    review_payloads: list[dict[str, object]] = []

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
            return TelegramStarTransactionsPage(transactions=[_transaction()])

    async def _candidate_rows(*_args, **_kwargs):
        first = purchase_model(status="PRECHECKOUT_OK", stars_amount=29, invoice_payload="a")
        second = purchase_model(status="PRECHECKOUT_OK", stars_amount=29, invoice_payload="b")
        for purchase in (first, second):
            purchase.created_at = datetime(2026, 7, 7, 11, 55, tzinfo=timezone.utc)
        return [(first, 270), (second, 270)]

    async def _apply_successful_payment(*_args, **_kwargs):
        raise AssertionError("ambiguous match must not auto-credit")

    async def _create_review_once(
        session: object,
        *,
        event_type: str,
        payload: dict[str, object],
        payload_key: str,
        status: str,
    ):
        del session, event_type, payload_key, status
        review_payloads.append(payload)
        return object(), True

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _candidate_rows,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result["auto_recovery_counts"] == {"not_exact_match": 1}
    assert result["review_findings"] == 1
    assert result["review_events_created"] == 1
    assert review_payloads[0]["reason"] == "AMBIGUOUS_MATCH"


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_auto_revalidates_locked_candidates(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: _settings(enabled=True, dry_run=False, auto_recovery_enabled=True),
    )
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    first = purchase_model(status="PRECHECKOUT_OK", stars_amount=29, invoice_payload="invoice-1")
    second = purchase_model(status="PRECHECKOUT_OK", stars_amount=29, invoice_payload="invoice-2")
    for purchase in (first, second):
        purchase.created_at = datetime(2026, 7, 7, 11, 55, tzinfo=timezone.utc)
    candidate_calls = 0
    review_payloads: list[dict[str, object]] = []

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
            return TelegramStarTransactionsPage(transactions=[_transaction()])

    async def _candidate_rows(*_args, **_kwargs):
        nonlocal candidate_calls
        candidate_calls += 1
        return [(first, 270)] if candidate_calls == 1 else [(first, 270), (second, 270)]

    async def _apply_successful_payment(*_args, **_kwargs):
        raise AssertionError("changed locked candidate set must not auto-credit")

    async def _create_review_once(
        session: object,
        *,
        event_type: str,
        payload: dict[str, object],
        payload_key: str,
        status: str,
    ):
        del session, event_type, payload_key, status
        review_payloads.append(payload)
        return object(), True

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _candidate_rows,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result["auto_recovery_counts"] == {"revalidation_failed": 1}
    assert result["review_events_created"] == 1
    assert review_payloads[0]["reason"] == "WOULD_RECOVER_EXACT_MATCH"


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_auto_blocks_credited_charge_conflict(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        payments_reliability_async,
        "get_settings",
        lambda: _settings(enabled=True, dry_run=False, auto_recovery_enabled=True),
    )
    monkeypatch.setattr(payments_reliability_async, "SessionLocal", _SessionLocal())
    purchase = purchase_model(status="PRECHECKOUT_OK", stars_amount=29, invoice_payload="invoice-1")
    purchase.created_at = datetime(2026, 7, 7, 11, 55, tzinfo=timezone.utc)
    candidate_calls = 0
    review_payloads: list[dict[str, object]] = []

    class FakeStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
            return TelegramStarTransactionsPage(transactions=[_transaction()])

    async def _candidate_rows(*_args, **_kwargs):
        nonlocal candidate_calls
        candidate_calls += 1
        if candidate_calls == 2:
            purchase.status = "CREDITED"
            purchase.telegram_payment_charge_id = "different-charge"
        return [(purchase, 270)]

    async def _apply_successful_payment(*_args, **_kwargs):
        raise AssertionError("charge conflict must not auto-credit")

    async def _create_review_once(
        session: object,
        *,
        event_type: str,
        payload: dict[str, object],
        payload_key: str,
        status: str,
    ):
        del session, event_type, payload_key, status
        review_payloads.append(payload)
        return object(), True

    monkeypatch.setattr(payments_reliability_async, "TelegramStarsClient", FakeStarsClient)
    monkeypatch.setattr(
        payments_reliability_async.PurchasesRepo,
        "list_stars_reconciliation_candidate_rows",
        _candidate_rows,
    )
    monkeypatch.setattr(
        payments_reliability_async.PurchaseService,
        "apply_successful_payment",
        _apply_successful_payment,
    )
    monkeypatch.setattr(
        payments_reliability_async.OutboxEventsRepo,
        "create_once_by_payload_key",
        _create_review_once,
    )

    result = await payments_reliability_async.run_telegram_stars_reconciliation_async()

    assert result["auto_recovery_counts"] == {"revalidation_failed": 1}
    assert result["review_events_created"] == 1
    assert review_payloads[0]["reason"] == "WOULD_RECOVER_EXACT_MATCH"


@pytest.mark.asyncio
async def test_telegram_stars_reconciliation_reports_sanitized_client_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(payments_reliability_async, "get_settings", lambda: _settings(enabled=True))

    class FailingStarsClient:
        def __init__(self, *, bot_token: str) -> None:
            assert bot_token == "bot-token-secret"

        async def get_star_transactions(
            self,
            *,
            offset: int,
            limit: int,
        ) -> TelegramStarTransactionsPage:
            del offset, limit
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
