"""Builder pattern: assembles a valid, immutable Expense step by step.

build() is the only way to make a new Expense. It runs every invariant check
and either returns a frozen Expense or raises InvalidExpenseError /
InvalidSplitError / InvalidAmountError.
"""

from __future__ import annotations

from datetime import date, timedelta

from hisaab.domain.clock import Clock
from hisaab.domain.errors import InvalidAmountError, InvalidExpenseError
from hisaab.domain.models import Expense, SplitType
from hisaab.domain.money import MAX_EXPENSE_PAISA, Money
from hisaab.splitting.strategies import SplitStrategy

MAX_DESCRIPTION_LEN = 200
MAX_CATEGORY_LEN = 40
MAX_FUTURE_DAYS = 1  # allow for time-zone differences, nothing more


class ExpenseBuilder:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._group_id: int | None = None
        self._payer_id: int | None = None
        self._created_by: int | None = None
        self._amount: Money | None = None
        self._split_type: SplitType | None = None
        self._strategy: SplitStrategy | None = None
        self._participants: list[int] = []
        self._spent_on: date | None = None
        self._category: str | None = None
        self._description: str | None = None
        self._idempotency_key: str | None = None

    def in_group(self, group_id: int) -> ExpenseBuilder:
        self._group_id = group_id
        return self

    def paid_by(self, payer_id: int) -> ExpenseBuilder:
        self._payer_id = payer_id
        return self

    def created_by(self, user_id: int) -> ExpenseBuilder:
        self._created_by = user_id
        return self

    def amount(self, amount: Money) -> ExpenseBuilder:
        self._amount = amount
        return self

    def split(
        self, split_type: SplitType, strategy: SplitStrategy, participants: list[int]
    ) -> ExpenseBuilder:
        self._split_type = split_type
        self._strategy = strategy
        self._participants = list(participants)
        return self

    def on(self, spent_on: date | None) -> ExpenseBuilder:
        self._spent_on = spent_on
        return self

    def category(self, category: str | None) -> ExpenseBuilder:
        self._category = category
        return self

    def description(self, description: str | None) -> ExpenseBuilder:
        self._description = description
        return self

    def idempotency_key(self, key: str | None) -> ExpenseBuilder:
        self._idempotency_key = key
        return self

    def build(self) -> Expense:
        if self._group_id is None or self._payer_id is None or self._created_by is None:
            raise InvalidExpenseError("expense", "group, payer and creator are required")
        if self._amount is None:
            raise InvalidAmountError("amount", "is required")
        if not 1 <= self._amount.paisa <= MAX_EXPENSE_PAISA:
            raise InvalidAmountError("amount", "must be between 0.01 and 10,000,000.00 PKR")
        if self._strategy is None or self._split_type is None:
            raise InvalidExpenseError("split_type", "is required")
        today = self._clock.today()
        spent_on = self._spent_on or today
        if spent_on > today + timedelta(days=MAX_FUTURE_DAYS):
            raise InvalidExpenseError("spent_on", "cannot be in the future")
        description = _optional_text("description", self._description, MAX_DESCRIPTION_LEN)
        category = _optional_text("category", self._category, MAX_CATEGORY_LEN)

        shares = self._strategy.split(self._amount, self._participants, self._payer_id)

        return Expense(
            id=None,
            group_id=self._group_id,
            payer_id=self._payer_id,
            amount=self._amount,
            split_type=self._split_type,
            shares=tuple(shares),
            spent_on=spent_on,
            created_by=self._created_by,
            created_at=self._clock.now(),
            category=category,
            description=description,
            idempotency_key=self._idempotency_key,
        )


def _optional_text(field: str, value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) > max_len:
        raise InvalidExpenseError(field, f"must be at most {max_len} characters")
    return text or None
