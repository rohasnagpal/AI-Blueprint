from collections.abc import Callable
from threading import Event, Lock
from typing import Any

_lock = Lock()
_cancel_events: dict[str, Event] = {}
_running_jobs: set[str] = set()


def run_background_job(job_id: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    with _lock:
        _running_jobs.add(job_id)
        _cancel_events.setdefault(job_id, Event())
    try:
        return func(*args, **kwargs)
    finally:
        with _lock:
            _running_jobs.discard(job_id)
            event = _cancel_events.get(job_id)
            if event and event.is_set():
                _cancel_events.pop(job_id, None)


def request_job_cancel(job_id: str) -> bool:
    with _lock:
        event = _cancel_events.setdefault(job_id, Event())
        event.set()
        return job_id in _running_jobs


def is_cancel_requested(job_id: str) -> bool:
    with _lock:
        event = _cancel_events.get(job_id)
        return bool(event and event.is_set())


def is_job_running(job_id: str) -> bool:
    with _lock:
        return job_id in _running_jobs


def clear_job_control(job_id: str) -> None:
    with _lock:
        if job_id not in _running_jobs:
            _cancel_events.pop(job_id, None)
