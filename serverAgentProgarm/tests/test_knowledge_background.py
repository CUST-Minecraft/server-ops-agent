import threading

from app.knowledge.background import KnowledgeSyncCoordinator


def test_notify_runs_sync_without_blocking_and_coalesces_burst():
    started = threading.Event()
    release = threading.Event()
    calls = []

    def sync():
        calls.append(len(calls) + 1)
        started.set()
        release.wait(timeout=2)

    coordinator = KnowledgeSyncCoordinator(sync, debounce_seconds=0, retry_seconds=0)
    try:
        assert coordinator.notify() is True
        assert started.wait(timeout=2)
        assert coordinator.notify() is False
        release.set()
        coordinator.wait(timeout=2)
        assert len(calls) == 2
    finally:
        coordinator.stop()


def test_failed_sync_retries_without_raising_to_caller():
    attempts = []

    def sync():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("ollama temporarily unavailable")

    coordinator = KnowledgeSyncCoordinator(
        sync,
        debounce_seconds=0,
        retry_seconds=0,
        max_attempts=2,
    )
    try:
        assert coordinator.notify() is True
        coordinator.wait(timeout=2)
        assert len(attempts) == 2
    finally:
        coordinator.stop()
