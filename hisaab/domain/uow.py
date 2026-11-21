"""Unit of work: the one way services make a group-scoped change atomic.

A unit of work for a group (1) takes that group's lock from the LockRegistry and
(2) opens a database transaction. Services depend on this abstraction only; the
SQLite and in-memory versions live in hisaab/persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class UnitOfWork(ABC):
    @abstractmethod
    def for_group(self, group_id: int) -> AbstractContextManager[None]:
        """Serialise writes to one group and make them atomic."""

    @abstractmethod
    def read_snapshot(self) -> AbstractContextManager[None]:
        """A read-only transaction that sees one consistent point in time."""
