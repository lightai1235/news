"""信源共享 HTTP 工具：统一 UA、限速器（非官方接口 ≤1 req/s，SPEC §5.4）。"""

from __future__ import annotations

import threading
import time

UA = "OpenMind/0.1 (daily knowledge digest; +https://github.com/lightai1235/news)"
TIMEOUT = 10.0


class RateLimiter:
    """进程内线程安全限速：两次 acquire 之间至少间隔 min_interval 秒。"""

    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self) -> None:
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


def strip_html(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", " ", text).strip()
