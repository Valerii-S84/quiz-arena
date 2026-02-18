from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "quiz_arena",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.telegram_updates",
        "app.workers.tasks.payments_reliability",
        "app.workers.tasks.promo_maintenance",
    ],
)

celery_app.conf.update(
    task_default_queue="q_normal",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Berlin",
    enable_utc=True,
)


@celery_app.task(name="app.workers.celery_app.ping")
def ping() -> str:
    return "pong"
