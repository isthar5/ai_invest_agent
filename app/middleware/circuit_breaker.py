"""
Circuit Breaker — 熔断器中间件。

从 app/gateway 迁移至 app/middleware/。
提供 Closed → Open → Half-Open 三态状态机，
时间窗口错误率统计，Prometheus 集成。

用法：
    from app.middleware.circuit_breaker import get_cb

    cb = get_cb("go_tool")
    if not cb.allow_request():
        return fallback_response()
    try:
        result = do_call()
        cb.on_success()
    except Exception:
        cb.on_failure()
        raise
"""

import os
import time
import threading
from enum import Enum

# ── 配置（可通过环境变量覆盖） ──────────────────────

CB_CONFIG = {
    "recovery_time": int(os.getenv("CB_RECOVERY_TIME", "10")),
    "error_rate_threshold": float(os.getenv("CB_ERROR_RATE_THRESHOLD", "0.5")),
    "min_samples": int(os.getenv("CB_MIN_SAMPLES", "5")),
    "window_size": int(os.getenv("CB_WINDOW_SIZE", "60")),
    "half_open_probe_interval": int(os.getenv("CB_HALF_OPEN_PROBE_INTERVAL", "5")),
    "half_open_success_threshold": int(os.getenv("CB_HALF_OPEN_SUCCESS_THRESHOLD", "2")),
}


class State(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


_STATE_GAUGE_VALUE = {State.CLOSED: 0, State.OPEN: 1, State.HALF_OPEN: 0.5}


def _notify_state_change(service_key: str, new_state: State):
    try:
        from app.observability.metrics import cb_status_gauge
        cb_status_gauge.labels(service=service_key).set(_STATE_GAUGE_VALUE[new_state])
    except ImportError:
        pass


class CircuitBreaker:
    """线程安全的熔断器"""

    def __init__(self, service_key: str):
        self.service_key = service_key
        self.state = State.CLOSED
        self._lock = threading.Lock()

        # Closed state — time-windowed counters
        self._window_start = time.time()
        self._success_count = 0
        self._fail_count = 0

        # Open state
        self._opened_at = 0.0

        # Half-Open state
        self._half_open_successes = 0
        self._last_probe_time = 0.0

    # ── observability ────────────────────────────────────

    @property
    def fail_count(self) -> int:
        return self._fail_count

    @property
    def opened_at(self) -> float:
        return self._opened_at

    # ── public API ───────────────────────────────────────

    def allow_request(self) -> bool:
        with self._lock:
            now = time.time()

            if self.state == State.CLOSED:
                self._rotate_window_if_expired(now)
                return True

            if self.state == State.OPEN:
                if now - self._opened_at >= CB_CONFIG["recovery_time"]:
                    self._transition_to(State.HALF_OPEN)
                    self._last_probe_time = now
                    return True
                return False

            if self.state == State.HALF_OPEN:
                interval = CB_CONFIG["half_open_probe_interval"]
                if now - self._last_probe_time >= interval:
                    self._last_probe_time = now
                    return True
                return False

            return False

    def on_success(self):
        with self._lock:
            if self.state == State.CLOSED:
                self._success_count += 1

            elif self.state == State.HALF_OPEN:
                self._half_open_successes += 1
                threshold = CB_CONFIG["half_open_success_threshold"]
                if self._half_open_successes >= threshold:
                    self._transition_to(State.CLOSED)

    def on_failure(self):
        with self._lock:
            if self.state == State.CLOSED:
                self._fail_count += 1
                self._check_trip()

            elif self.state == State.HALF_OPEN:
                self._transition_to(State.OPEN)

    # ── internals ────────────────────────────────────────

    def _check_trip(self):
        total = self._success_count + self._fail_count
        min_samples = CB_CONFIG["min_samples"]
        if total < min_samples:
            return
        error_rate = self._fail_count / total
        threshold = CB_CONFIG["error_rate_threshold"]
        if error_rate >= threshold:
            self._transition_to(State.OPEN)

    def _rotate_window_if_expired(self, now: float):
        window_size = CB_CONFIG["window_size"]
        if now - self._window_start > window_size:
            self._window_start = now
            self._success_count = 0
            self._fail_count = 0

    def _transition_to(self, new_state: State):
        if self.state == new_state:
            return
        self.state = new_state

        if new_state == State.CLOSED:
            self._window_start = time.time()
            self._success_count = 0
            self._fail_count = 0
            self._half_open_successes = 0
        elif new_state == State.OPEN:
            self._opened_at = time.time()
        elif new_state == State.HALF_OPEN:
            self._half_open_successes = 0
            self._last_probe_time = 0.0

        _notify_state_change(self.service_key, new_state)


# ── per-service registry ────────────────────────────────

cb_map: dict[str, CircuitBreaker] = {}


def get_cb(service_key: str) -> CircuitBreaker:
    if service_key not in cb_map:
        cb_map[service_key] = CircuitBreaker(service_key)
    return cb_map[service_key]
