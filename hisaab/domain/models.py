"""Immutable domain objects shared by all modules.

All are frozen dataclasses so they can be passed between worker threads
without one thread changing an object another thread is reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from hisaab.domain.money import Money


class SplitType(StrEnum):
    EQUAL = "equal"
    EXACT = "exact"
    PERCENT = "percent"
    SHARES = "shares"


class ExpenseStatus(StrEnum):
    ACTIVE = "active"
    VOIDED = "voided"


class LedgerSource(StrEnum):
    EXPENSE = "expense"
    VOID = "void"
    SETTLEMENT = "settlement"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class Group:
    id: int
    name: str
    admin_id: int
    created_at: datetime


@dataclass(frozen=True)
class Share:
    user_id: int
    amount: Money


@dataclass(frozen=True)
class Expense:
    """A finished, valid expense. Only ExpenseBuilder.build() creates new ones."""

    id: int | None
    group_id: int
    payer_id: int
    amount: Money
    split_type: SplitType
    shares: tuple[Share, ...]
    spent_on: date
    created_by: int
    created_at: datetime
    category: str | None = None
    description: str | None = None
    idempotency_key: str | None = None
    status: ExpenseStatus = ExpenseStatus.ACTIVE

    @property
    def participant_ids(self) -> list[int]:
        return [s.user_id for s in self.shares]


@dataclass(frozen=True)
class LedgerEntry:
    """One row of the append-only ledger. Positive = the group owes this user."""

    group_id: int
    user_id: int
    amount: Money
    source_type: LedgerSource
    source_id: int
    created_at: datetime
    id: int | None = None


@dataclass(frozen=True)
class Transfer:
    """A suggested or recorded payment from one member to another."""

    from_user_id: int
    to_user_id: int
    amount: Money


@dataclass(frozen=True)
class Settlement:
    id: int | None
    group_id: int
    from_user_id: int
    to_user_id: int
    amount: Money
    created_at: datetime


@dataclass(frozen=True)
class ReportJob:
    id: int | None
    group_id: int
    period: str  # YYYY-MM
    format: str
    status: JobStatus
    requested_by: int
    created_at: datetime
    file_path: str | None = None
    error: str | None = None
    finished_at: datetime | None = None
