"""Celery app wiring tests."""

from __future__ import annotations

from worker.celery_app import _resolve_celery_log_file_name


def test_resolve_celery_log_file_name_for_worker() -> None:
    assert _resolve_celery_log_file_name(["celery", "-A", "worker.celery_app", "worker"]) == "celery-worker.log"


def test_resolve_celery_log_file_name_for_beat() -> None:
    assert _resolve_celery_log_file_name(["celery", "-A", "worker.celery_app", "beat"]) == "celery-beat.log"


def test_resolve_celery_log_file_name_for_other_commands() -> None:
    assert _resolve_celery_log_file_name(["celery", "-A", "worker.celery_app", "call", "task"]) == "celery.log"
