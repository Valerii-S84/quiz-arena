from __future__ import annotations


def build_pagination(*, total: int, page: int, limit: int) -> dict[str, int]:
    resolved_page = max(1, int(page))
    resolved_limit = max(1, min(200, int(limit)))
    pages = max(1, (max(0, total) + resolved_limit - 1) // resolved_limit)
    return {
        "total": max(0, total),
        "page": resolved_page,
        "pages": pages,
        "limit": resolved_limit,
    }
