"""Worker tasks package.

Keep this package init lightweight to avoid import cycles between bot handlers
and task modules. Import concrete task modules directly, for example:
`from app.workers.tasks import telegram_updates`.
"""

