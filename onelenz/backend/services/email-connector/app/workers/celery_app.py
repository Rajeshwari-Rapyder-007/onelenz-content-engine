import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
SYNC_FREQUENCY_MINUTES = int(os.getenv("SYNC_FREQUENCY_MINUTES", "15"))

celery = Celery(
    "email_connector",
    broker=CELERY_BROKER_URL,
    backend=CELERY_BROKER_URL,
    include=["app.workers.sync_tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

BEAT_ENABLED = os.getenv("BEAT_ENABLED", "true").lower() == "true"

if BEAT_ENABLED:
    celery.conf.beat_schedule = {
        "incremental_sync_all": {
            "task": "app.workers.sync_tasks.incremental_sync_all",
            "schedule": SYNC_FREQUENCY_MINUTES * 60,  # seconds
        },
    }
