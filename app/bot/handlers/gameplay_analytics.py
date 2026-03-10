from __future__ import annotations


async def emit_analytics_event(*args, **kwargs):
    from app.core.analytics_events import emit_analytics_event as _emit_analytics_event

    await _emit_analytics_event(*args, **kwargs)
