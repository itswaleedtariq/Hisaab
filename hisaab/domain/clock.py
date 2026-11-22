"""Clock abstraction so tests can use a fixed time (DIP)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...

    def today(self) -> date:
        return self.now().date()


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock(Clock):
    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at
