import logging
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from prometheus_client import Counter

logger = logging.getLogger(__name__)

CB_OPEN_TOTAL = Counter("omnicall_circuit_open_total", "Circuit breaker open events", ["name"])
CB_REJECT_TOTAL = Counter("omnicall_circuit_reject_total", "Requests rejected by circuit breaker", ["name"])
CB_RECOVERY_SUCCESS = Counter("omnicall_circuit_recovery_success_total", "Successful recovery calls", ["name"])
CB_RECOVERY_FAILURE = Counter("omnicall_circuit_recovery_failure_total", "Failed recovery calls", ["name"])


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""

    def __init__(self, name: str, remaining_seconds: float) -> None:
        self.name = name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit breaker '{name}' is open. "
            f"Retry in {remaining_seconds:.0f} seconds."
        )


class _State(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Generic circuit breaker for wrapping external calls.

    States:
        CLOSED   – normal operation, failures are counted.
        OPEN     – calls fail fast with CircuitBreakerOpenError.
        HALF_OPEN – one test call is allowed through.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_seconds: int = 30,
        enabled: bool = True,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.enabled = enabled

        self._state = _State.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == _State.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.recovery_seconds:
                    self._state = _State.HALF_OPEN
            return str(self._state)

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self.enabled:
            return func(*args, **kwargs)

        with self._lock:
            if self._state == _State.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.recovery_seconds:
                    self._state = _State.HALF_OPEN
                    logger.info("Circuit breaker '%s' transitioning to HALF_OPEN", self.name)
                else:
                    remaining = self.recovery_seconds - elapsed
                    CB_REJECT_TOTAL.labels(name=self.name).inc()
                    raise CircuitBreakerOpenError(self.name, remaining)

        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            if self._state == _State.HALF_OPEN:
                logger.info("Circuit breaker '%s' recovered, transitioning to CLOSED", self.name)
                CB_RECOVERY_SUCCESS.labels(name=self.name).inc()
            self._state = _State.CLOSED

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._state == _State.HALF_OPEN:
                logger.warning("Circuit breaker '%s' test call failed, reopening", self.name)
                self._state = _State.OPEN
                self._opened_at = time.monotonic()
                CB_RECOVERY_FAILURE.labels(name=self.name).inc()
            elif self._failure_count >= self.failure_threshold:
                logger.warning(
                    "Circuit breaker '%s' reached failure threshold (%d), opening",
                    self.name,
                    self.failure_count,
                )
                self._state = _State.OPEN
                self._opened_at = time.monotonic()
                CB_OPEN_TOTAL.labels(name=self.name).inc()
