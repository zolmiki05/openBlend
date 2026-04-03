"""
Exponential backoff utilities for HTTP rate-limit handling.
"""

import random
import time


def backoff_sleep(attempt: int, base: float = 1.0, cap: float = 60.0) -> None:
    """
    Sleep for base * 2^attempt seconds with ±25% jitter, capped at `cap` seconds.
    Use as: for attempt in range(MAX_RETRIES): ... backoff_sleep(attempt)
    """
    delay = base * (2 ** attempt)
    delay *= 0.75 + random.random() * 0.5  # 75–125% jitter
    time.sleep(min(delay, cap))
