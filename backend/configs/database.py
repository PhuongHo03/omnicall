from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.configs.settings import get_settings
from backend.providers.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from backend.utils.exceptions import ApplicationError


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_db_breaker = CircuitBreaker(
    "postgres",
    failure_threshold=settings.circuit_breaker_failure_threshold,
    recovery_seconds=settings.circuit_breaker_recovery_seconds,
    enabled=settings.circuit_breaker_enabled,
)


def get_db_session() -> Generator[Session, None, None]:
    try:
        session = _db_breaker.call(SessionLocal)
    except CircuitBreakerOpenError as exc:
        raise ApplicationError(503, "service_unavailable", "Database is temporarily unavailable. Please try again later.") from exc
    try:
        yield session
    finally:
        session.close()
