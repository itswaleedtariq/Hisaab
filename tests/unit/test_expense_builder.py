"""ExpenseBuilder: every invariant is checked in build() (FR-04)."""

from datetime import date

import pytest

from hisaab.domain.errors import InvalidAmountError, InvalidExpenseError
from hisaab.domain.models import SplitType
from hisaab.domain.money import Money
from hisaab.expenses.builder import ExpenseBuilder
from hisaab.splitting.strategies import EqualSplit


def builder(clock, paisa=1000):
    return (
        ExpenseBuilder(clock)
        .in_group(1)
        .paid_by(1)
        .created_by(1)
        .amount(Money(paisa))
        .split(SplitType.EQUAL, EqualSplit(), [1, 2])
    )


def test_build_returns_frozen_expense_with_defaults(clock):
    expense = builder(clock).build()
    assert expense.id is None
    assert expense.spent_on == date(2026, 11, 15)
    assert [s.amount.paisa for s in expense.shares] == [500, 500]
    with pytest.raises(AttributeError):
        expense.amount = Money(1)  # frozen


@pytest.mark.parametrize(
    ("paisa", "ok"),
    [
        pytest.param(0, False, id="TC-BB-14 amount 0.00"),
        pytest.param(1, True, id="TC-BB-15 amount 0.01"),
        pytest.param(1_000_000_000, True, id="TC-BB-16 amount 10,000,000.00"),
        pytest.param(1_000_000_001, False, id="TC-BB-17 amount 10,000,000.01"),
        pytest.param(-100, False, id="TC-BB-18 negative amount"),
    ],
)
def test_amount_boundaries(clock, paisa, ok):
    if ok:
        assert builder(clock, paisa).build().amount.paisa == paisa
    else:
        with pytest.raises(InvalidAmountError):
            builder(clock, paisa).build()


def test_missing_parts_are_rejected(clock):
    with pytest.raises(InvalidExpenseError):
        ExpenseBuilder(clock).amount(Money(1)).build()
    with pytest.raises(InvalidAmountError):
        ExpenseBuilder(clock).in_group(1).paid_by(1).created_by(1).build()
    with pytest.raises(InvalidExpenseError):
        ExpenseBuilder(clock).in_group(1).paid_by(1).created_by(1).amount(Money(5)).build()


def test_future_date_and_long_text_are_rejected(clock):
    with pytest.raises(InvalidExpenseError, match="spent_on"):
        builder(clock).on(date(2026, 12, 1)).build()
    with pytest.raises(InvalidExpenseError, match="description"):
        builder(clock).description("x" * 201).build()
    with pytest.raises(InvalidExpenseError, match="category"):
        builder(clock).category("x" * 41).build()


def test_optional_text_is_trimmed_and_blank_becomes_none(clock):
    expense = builder(clock).description("  dinner ").category("   ").build()
    assert expense.description == "dinner"
    assert expense.category is None
