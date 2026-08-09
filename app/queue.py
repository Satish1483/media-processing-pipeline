from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional


class InMemoryQueue:
    def __init__(self):
        self._jobs: Deque[Callable[[], None]] = deque()
        self._lock = threading.Lock()
        self._worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._worker_thread.start()

    def enqueue(self, func: Callable[[], None]) -> None:
        with self._lock:
            self._jobs.append(func)

    def _process_loop(self) -> None:
        while True:
            if not self._jobs:
                time.sleep(0.1)
                continue
            with self._lock:
                if not self._jobs:
                    continue
                job = self._jobs.popleft()
            try:
                job()
            except Exception:
                import logging

                logging.exception("Background job failed")


queue = InMemoryQueue()
