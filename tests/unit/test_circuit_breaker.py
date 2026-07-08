"""
Circuit breaker unit tests.

Run from the project root::

    python -m pytest tests/unit/test_circuit_breaker.py -v
"""

from unittest.mock import patch

from app.middleware.circuit_breaker import CircuitBreaker, State


# ── helpers ─────────────────────────────────────────────────────

def _trip_to_open(cb: CircuitBreaker) -> None:
    """Simulate enough failures to trip Closed → Open."""
    for _ in range(5):
        cb.allow_request()
        cb.on_failure()
    assert cb.state == State.OPEN


# ── Closed → Open ───────────────────────────────────────────────

def test_closed_to_open_on_high_error_rate():
    """Trip to Open when error rate >= 50% with >= 5 samples."""
    cb = CircuitBreaker("svc")
    assert cb.state == State.CLOSED

    for _ in range(5):
        cb.allow_request()
        cb.on_failure()

    assert cb.state == State.OPEN
    assert cb.opened_at > 0


def test_closed_stays_closed_below_threshold():
    """Stay Closed when error rate is below 50%."""
    cb = CircuitBreaker("svc")

    # 3 successes, 2 failures → error rate 40%
    for _ in range(3):
        cb.allow_request()
        cb.on_success()
    for _ in range(2):
        cb.allow_request()
        cb.on_failure()

    assert cb.state == State.CLOSED


def test_closed_stays_closed_insufficient_samples():
    """Stay Closed when total requests < min_samples even if all fail."""
    cb = CircuitBreaker("svc")

    for _ in range(4):
        cb.allow_request()
        cb.on_failure()

    assert cb.state == State.CLOSED


# ── Open state ──────────────────────────────────────────────────

def test_open_blocks_all_requests():
    """Open state rejects every request."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    for _ in range(10):
        assert cb.allow_request() is False


def test_open_to_half_open_after_recovery():
    """Open transitions to Half-Open once recovery_time has elapsed."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        mock_time.return_value = cb.opened_at + 11  # recovery_time=10

        assert cb.allow_request() is True
        assert cb.state == State.HALF_OPEN


# ── Half-Open: traffic control ──────────────────────────────────

def test_half_open_only_allows_one_probe_per_interval():
    """In Half-Open, only one request per probe interval is allowed."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        # Enter Half-Open
        base = cb.opened_at + 11
        mock_time.return_value = base
        assert cb.allow_request() is True
        assert cb.state == State.HALF_OPEN

        # Same timestamp — blocked
        assert cb.allow_request() is False

        # 4 s later — still within the 5 s interval
        mock_time.return_value = base + 4
        assert cb.allow_request() is False

        # 5 s later — new probe allowed
        mock_time.return_value = base + 5
        assert cb.allow_request() is True

        # Immediately after — blocked again
        assert cb.allow_request() is False

        # Another 5 s — third probe
        mock_time.return_value = base + 10
        assert cb.allow_request() is True

        # After that — blocked
        assert cb.allow_request() is False


# ── Half-Open → Closed via consecutive successes ────────────────

def test_half_open_to_closed_on_consecutive_success():
    """Half-Open returns to Closed after M consecutive probe successes."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        base = cb.opened_at + 11

        # Probe 1 — success
        mock_time.return_value = base
        assert cb.allow_request() is True
        cb.on_success()
        assert cb.state == State.HALF_OPEN  # need 2 consecutive

        # Probe 2 — success (triggers → Closed)
        mock_time.return_value = base + 5
        assert cb.allow_request() is True
        cb.on_success()
        assert cb.state == State.CLOSED

        # After recovery, all requests allowed
        assert cb.allow_request() is True


# ── Half-Open → Open on failure ─────────────────────────────────

def test_half_open_failure_returns_to_open():
    """A single probe failure in Half-Open immediately trips back to Open."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        base = cb.opened_at + 11

        # Enter Half-Open
        mock_time.return_value = base
        assert cb.allow_request() is True
        assert cb.state == State.HALF_OPEN

        # Probe fails → immediately Open
        cb.on_failure()
        assert cb.state == State.OPEN

        # opened_at was reset
        assert cb.opened_at == base

        # Further requests blocked
        assert cb.allow_request() is False


def test_half_open_resets_recovery_timer_on_failure():
    """After Half-Open → Open, the full recovery_time must pass again."""
    cb = CircuitBreaker("svc")
    _trip_to_open(cb)

    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        # Enter Half-Open
        base = cb.opened_at + 11
        mock_time.return_value = base
        cb.allow_request()
        cb.on_failure()
        assert cb.state == State.OPEN

        # Only 5 s passed — still within recovery_time
        mock_time.return_value = base + 5
        assert cb.allow_request() is False

        # Full recovery_time (10 s) after the new opened_at
        mock_time.return_value = base + 10
        assert cb.allow_request() is True
        assert cb.state == State.HALF_OPEN


# ── Window rotation ─────────────────────────────────────────────

def test_window_reset_after_expiry_prevents_trip():
    """Old failures expire and don't contribute to the trip threshold."""
    with patch("app.middleware.circuit_breaker.time.time") as mock_time:
        base = 1000.0
        mock_time.return_value = base
        cb = CircuitBreaker("svc")  # 必须在 patch 内创建，_window_start 才用 mock 时间

        # 3 failures in current window
        for _ in range(3):
            cb.allow_request()
            cb.on_failure()

        # Window expires
        mock_time.return_value = base + 61  # window_size=60

        # 2 more failures in the new window — total 2, < min_samples
        for _ in range(2):
            cb.allow_request()
            cb.on_failure()

        assert cb.state == State.CLOSED

        # 3 more failures — total 5 in this window, should trip
        for _ in range(3):
            cb.allow_request()
            cb.on_failure()

        assert cb.state == State.OPEN
