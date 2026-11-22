"""Ledger and settlement repositories.

LedgerReader is the read-only side. Users and Groups, Reports and the
SettlementFacade depend only on it, so they cannot write to the ledger (ISP).
"""

from __future__ import annotations

import dataclasses
import itertools
import threading
from abc import ABC, abstractmethod
from collections import defaultdict

from hisaab.domain.models import LedgerEntry, Settlement
from hisaab.domain.money import Money


class LedgerReader(ABC):
    @abstractmethod
    def balances(self, group_id: int) -> dict[int, Money]:
        """Current balance per user who has any ledger entry in the group."""

    def balance_of(self, group_id: int, user_id: int) -> Money:
        return self.balances(group_id).get(user_id, Money.zero())


class LedgerRepository(LedgerReader):
    @abstractmethod
    def append(self, entries: list[LedgerEntry]) -> None:
        """Insert entries. Rows are never updated or deleted."""

    @abstractmethod
    def entries(self, group_id: int) -> list[LedgerEntry]: ...


class SettlementRepository(ABC):
    @abstractmethod
    def add(self, settlement: Settlement) -> Settlement: ...

    @abstractmethod
    def list_for_group(self, group_id: int) -> list[Settlement]: ...


class InMemoryLedgerRepository(LedgerRepository):
    def __init__(self) -> None:
        self._rows: list[LedgerEntry] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def append(self, entries: list[LedgerEntry]) -> None:
        with self._lock:
            for entry in entries:
                self._rows.append(dataclasses.replace(entry, id=next(self._ids)))

    def entries(self, group_id: int) -> list[LedgerEntry]:
        with self._lock:
            return [e for e in self._rows if e.group_id == group_id]

    def balances(self, group_id: int) -> dict[int, Money]:
        totals: dict[int, int] = defaultdict(int)
        for entry in self.entries(group_id):
            totals[entry.user_id] += entry.amount.paisa
        return {uid: Money(p) for uid, p in totals.items()}


class InMemorySettlementRepository(SettlementRepository):
    def __init__(self) -> None:
        self._rows: list[Settlement] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, settlement: Settlement) -> Settlement:
        with self._lock:
            stored = dataclasses.replace(settlement, id=next(self._ids))
            self._rows.append(stored)
            return stored

    def list_for_group(self, group_id: int) -> list[Settlement]:
        with self._lock:
            return [s for s in self._rows if s.group_id == group_id]
