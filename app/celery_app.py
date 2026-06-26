"""Instância do Celery — usa o Redis como broker e backend de resultados."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "solara",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="solara",
    # Resposta de uma mensagem não deve travar para sempre
    task_soft_time_limit=90,
    task_time_limit=120,
)
