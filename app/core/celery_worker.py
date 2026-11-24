from celery import Celery

import app.models

from app.core.config import settings


celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.email_tasks"
    ],
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    beat_schedule={
        "recover-stale-email-processing-every-minute": {
            "task": "app.workers.email_tasks.recover_stale_email_tasks",
            "schedule": 60.0,
        },
    },
)
