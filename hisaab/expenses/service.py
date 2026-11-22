"""Expenses module (FR-04, FR-09, FR-16). Owner: Muhammad Abdullah."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Protocol

from hisaab.domain.clock import Clock
from hisaab.domain.errors import (
    ConflictError,
    ExpenseAlreadyVoidedError,
    ExpenseNotFoundError,
    InvalidSplitError,
    NotGroupAdminError,
    NotGroupMemberError,
)
from hisaab.domain.models import Expense, ExpenseStatus, Group, SplitType
from hisaab.domain.money import Money
from hisaab.domain.uow import UnitOfWork
from hisaab.events.bus import EventPublisher
from hisaab.events.events import ExpenseRecorded, ExpenseVoided
from hisaab.expenses.builder import ExpenseBuilder
from hisaab.expenses.repository import ExpenseRepository
from hisaab.splitting.factory import SplitStrategyFactory

logger = logging.getLogger(__name__)


class Membership(Protocol):
    """The part of GroupService that Expenses needs (ISP)."""

    def require_member(self, group_id: int, user_id: int) -> Group: ...

    def members(self, group_id: int, actor_id: int) -> list[int]: ...

    def ensure_can_record_expenses(self, group_id: int) -> None: ...


@dataclass(frozen=True)
class NewExpense:
    """Input for ExpenseService.record (already parsed by the API layer)."""

    group_id: int
    payer_id: int
    amount: Money
    split_type: str
    participants: list[int]
    split_params: Mapping[str, Any] = field(default_factory=dict)
    spent_on: date | None = None
    category: str | None = None
    description: str | None = None
    idempotency_key: str | None = None


class ExpenseService:
    def __init__(
        self,
        expenses: ExpenseRepository,
        membership: Membership,
        factory: SplitStrategyFactory,
        publisher: EventPublisher,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._expenses = expenses
        self._membership = membership
        self._factory = factory
        self._publisher = publisher
        self._uow = uow
        self._clock = clock

    def record(self, data: NewExpense, actor_id: int) -> Expense:
        """FR-04 + FR-16. Returns the existing expense for a repeated idempotency key."""
        with self._uow.for_group(data.group_id):
            # Membership first, so a replayed key cannot reveal another group's data (DEF-01).
            self._membership.require_member(data.group_id, actor_id)
            if data.idempotency_key:
                existing = self._expenses.find_by_idempotency_key(data.idempotency_key)
                if existing is not None:
                    if existing.group_id != data.group_id:
                        raise ConflictError("idempotency key already used in another group")
                    logger.info("idempotent replay key=%s", data.idempotency_key)
                    return existing

            self._membership.ensure_can_record_expenses(data.group_id)
            members = set(self._membership.members(data.group_id, actor_id))
            if data.payer_id not in members:
                raise NotGroupMemberError(f"payer {data.payer_id} is not a group member")
            outsiders = [p for p in data.participants if p not in members]
            if outsiders:
                raise NotGroupMemberError(f"participants {outsiders} are not group members")

            try:
                split_type = SplitType(data.split_type)
            except ValueError as exc:
                raise InvalidSplitError(
                    "split_type", f"must be one of {', '.join(self._factory.supported())}"
                ) from exc
            strategy = self._factory.create(data.split_type, data.split_params)

            expense = (
                ExpenseBuilder(self._clock)
                .in_group(data.group_id)
                .paid_by(data.payer_id)
                .created_by(actor_id)
                .amount(data.amount)
                .split(split_type, strategy, data.participants)
                .on(data.spent_on)
                .category(data.category)
                .description(data.description)
                .idempotency_key(data.idempotency_key)
                .build()
            )
            saved = self._expenses.add(expense)
            self._publisher.publish(ExpenseRecorded(saved))
            logger.info("expense recorded id=%s group=%s", saved.id, saved.group_id)
            return saved

    def void(self, expense_id: int, actor_id: int) -> Expense:
        """FR-09: admin or creator only; adds reversing ledger entries via the event."""
        found = self._get(expense_id)
        with self._uow.for_group(found.group_id):
            expense = self._get(expense_id)  # re-read under the lock
            group = self._membership.require_member(expense.group_id, actor_id)
            if actor_id not in (group.admin_id, expense.created_by):
                raise NotGroupAdminError("only the group admin or the creator can void")
            if expense.status is ExpenseStatus.VOIDED:
                raise ExpenseAlreadyVoidedError(f"expense {expense_id} is already voided")
            self._expenses.set_status(expense_id, ExpenseStatus.VOIDED)
            voided = replace(expense, status=ExpenseStatus.VOIDED)
            self._publisher.publish(ExpenseVoided(voided, voided_by=actor_id))
            logger.info("expense voided id=%s by=%s", expense_id, actor_id)
            return voided

    def get(self, expense_id: int, actor_id: int) -> Expense:
        expense = self._get(expense_id)
        self._membership.require_member(expense.group_id, actor_id)
        return expense

    def list_for_group(self, group_id: int, actor_id: int) -> list[Expense]:
        self._membership.require_member(group_id, actor_id)
        return self._expenses.list_for_group(group_id)

    def _get(self, expense_id: int) -> Expense:
        expense = self._expenses.get(expense_id)
        if expense is None:
            raise ExpenseNotFoundError(f"expense {expense_id} not found")
        return expense
