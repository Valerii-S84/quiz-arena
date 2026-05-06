from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes.public_contact_payload import (
    ContactPayload,
    is_honeypot_triggered,
    normalize_contact_payload,
    validate_contact_payload,
)


def _student_payload(**overrides: object) -> ContactPayload:
    payload: dict[str, object] = {
        "type": "student",
        "name": "Max",
        "contact": "@max",
        "ageGroup": "16-25",
        "level": "A2",
        "goals": ["Alltagssprache"],
        "format": "Individuell",
        "timeSlots": ["Abend"],
        "frequency": "2x pro Woche",
    }
    payload.update(overrides)
    return ContactPayload.model_validate(payload)


def _partner_payload(**overrides: object) -> ContactPayload:
    payload: dict[str, object] = {
        "type": "partner",
        "name": "Org",
        "contact": "org@example.com",
        "country": "Deutschland",
        "studentCount": "50+",
        "offerings": ["Unterricht"],
        "idea": "Kooperation",
        "startTimeline": "Sofort",
        "cooperationType": "Sprachschule",
        "company": "   ",
    }
    payload.update(overrides)
    return ContactPayload.model_validate(payload)


def test_validate_contact_payload_rejects_student_payload_with_only_blank_list_items() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_contact_payload(_student_payload(goals=[" ", "\t"], timeSlots=["Abend"]))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "E_GOALS_REQUIRED"}


def test_validate_contact_payload_accepts_partner_cooperation_type_fallback() -> None:
    validate_contact_payload(_partner_payload(partnerType=" ", cooperationType="Schule"))


def test_normalize_contact_payload_uses_first_non_blank_partner_type_and_strips_honeypot() -> None:
    normalized = normalize_contact_payload(
        _partner_payload(partnerType=" ", cooperationType="Schule", company="Spam Corp")
    )

    assert normalized["partnerType"] == "Schule"
    assert normalized["cooperationType"] == "Schule"
    assert "company" not in normalized


def test_is_honeypot_triggered_ignores_blank_values_and_flags_non_blank_input() -> None:
    assert is_honeypot_triggered(_student_payload(company="   ")) is False
    assert is_honeypot_triggered(_student_payload(company="bot")) is True
