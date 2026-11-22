"""Domain events published on the in-process event bus."""

from __future__ import annotations

from dataclasses import dataclass

from hisaab.domain.models import Expense, Settlement


@dataclass(frozen=True)
class ExpenseRecorded:
    expense: Expense


@dataclass(frozen=True)
class ExpenseVoided:
    expense: Expense
    voided_by: int


@dataclass(frozen=True)
class SettlementRecorded:
    settlement: Settlement
