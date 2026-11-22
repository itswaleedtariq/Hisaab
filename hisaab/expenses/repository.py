"""Repository interface for Expenses."""

from __future__ import annotations

import dataclasses
import itertools
import threading
from abc import ABC, abstractmethod

from hisaab.domain.models import Expense, ExpenseStatus


class ExpenseRepository(ABC):
    @abstractmethod
    def add(self, expense: Expense) -> Expense:
        """Store the expense and its shares; return it with its new id."""

    @abstractmethod
    def get(self, expense_id: int) -> Expense | None: ...

    @abstractmethod
    def find_by_idempotency_key(self, key: str) -> Expense | None: ...

    @abstractmethod
    def set_status(self, expense_id: int, status: ExpenseStatus) -> None: ...

    @abstractmethod
    def list_for_group(self, group_id: int, period: str | None = None) -> list[Expense]:
        """Expenses of a group, oldest first. ``period`` is 'YYYY-MM' to filter by month."""


class InMemoryExpenseRepository(ExpenseRepository):
    def __init__(self) -> None:
        self._rows: dict[int, Expense] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, expense: Expense) -> Expense:
        with self._lock:
            stored = dataclasses.replace(expense, id=next(self._ids))
            self._rows[stored.id] = stored  # type: ignore[index]
            return stored

    def get(self, expense_id: int) -> Expense | None:
        return self._rows.get(expense_id)

    def find_by_idempotency_key(self, key: str) -> Expense | None:
        with self._lock:
            return next((e for e in self._rows.values() if e.idempotency_key == key), None)

    def set_status(self, expense_id: int, status: ExpenseStatus) -> None:
        with self._lock:
            self._rows[expense_id] = dataclasses.replace(self._rows[expense_id], status=status)

    def list_for_group(self, group_id: int, period: str | None = None) -> list[Expense]:
        with self._lock:
            rows = [e for e in self._rows.values() if e.group_id == group_id]
        if period:
            rows = [e for e in rows if e.spent_on.strftime("%Y-%m") == period]
        return sorted(rows, key=lambda e: e.id or 0)
