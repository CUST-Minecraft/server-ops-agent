"""Small in-process background coordinator for recovery index sync."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

logger = logging.getLogger(__name__)


class KnowledgeSyncCoordinator:
    """Coalesce recovery events onto one non-blocking sync worker.

    The database remains the durable source of pending cases. This object only
    coordinates process-local wakeups; a new process can notify on startup.
    """

    def __init__(
        self,
        sync_fn: Callable[[], object],
        debounce_seconds: float = 3.0,
        retry_seconds: float = 30.0,
        max_attempts: int = 3,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.sync_fn = sync_fn
        self.debounce_seconds = max(0.0, debounce_seconds)
        self.retry_seconds = max(0.0, retry_seconds)
        self.max_attempts = max(1, max_attempts)
        self.sleep_fn = sleep_fn
        self._lock = threading.Lock()
        self._dirty = False
        self._stopped = False
        self._future: Future | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="recovery-index",
        )

    def notify(self) -> bool:
        """Schedule a sync without waiting; return whether a worker was created."""
        with self._lock:
            if self._stopped:
                return False
            self._dirty = True
            if self._future is not None and not self._future.done():
                return False
            self._future = self._executor.submit(self._run)
            return True

    def _run(self) -> None:
        self.sleep_fn(self.debounce_seconds)
        while True:
            with self._lock:
                self._dirty = False
            self._sync_with_retry()
            with self._lock:
                again = self._dirty and not self._stopped
            if not again:
                return
            self.sleep_fn(self.debounce_seconds)

    def _sync_with_retry(self) -> None:
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.sync_fn()
                return
            except Exception:  # noqa: BLE001 - background work must not kill Runner
                logger.exception(
                    "recovery index sync failed attempt=%s/%s",
                    attempt,
                    self.max_attempts,
                )
                if attempt < self.max_attempts:
                    self.sleep_fn(self.retry_seconds)

    def wait(self, timeout: float | None = None) -> None:
        future = self._future
        if future is not None:
            future.result(timeout=timeout)

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self._executor.shutdown(wait=True)
