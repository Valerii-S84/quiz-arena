from __future__ import annotations


def payload_metadata(value: str | None) -> dict[str, object]:
    if value is None:
        return {"present": False}
    return {
        "present": True,
        "length": len(value),
        "starts_with_slash": value.startswith("/"),
    }


def scalar_metadata(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    return {"type": type(value).__name__}
