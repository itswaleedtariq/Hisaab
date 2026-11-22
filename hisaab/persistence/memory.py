"""In-memory unit of work used by the fast unit tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from hisaab.domain.uow import UnitOfWork
from hisaab.ledger.locks import LockRegistry


class InMemoryUnitOfWork(UnitOfWork):
    """Takes the group lock. In-memory repositories have no rollback."""

    def __init__(self, locks: LockRegistry) -> None:
        self._locks = locks

    @contextmanager
    def for_group(self, group_id: int) -> Iterator[None]:
        with self._locks.hold(group_id):
            yield

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        yield
