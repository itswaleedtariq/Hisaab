"""Unit of work through the composition root: the Observer handler runs inside
the publisher's transaction, so a failing handler leaves no half-saved expense."""

import pytest

from hisaab.domain.errors import HisaabError
from hisaab.domain.money import Money
from hisaab.events.events import ExpenseRecorded
from hisaab.expenses.service import NewExpense


def test_failed_ledger_handler_rolls_back_the_expense(sqlite_trip):
    """The Observer handler runs inside the same transaction (no half-saved expense)."""
    c = sqlite_trip.c

    def failing_handler(_event):
        raise HisaabError("ledger unavailable")

    c.bus.subscribe(ExpenseRecorded, failing_handler)
    with pytest.raises(HisaabError):
        c.expenses.record(
            NewExpense(sqlite_trip.group_id, sqlite_trip.ali, Money(900), "equal",
                       [sqlite_trip.ali, sqlite_trip.sara]),
            sqlite_trip.ali,
        )
    assert c.expenses.list_for_group(sqlite_trip.group_id, sqlite_trip.ali) == []
    assert c.ledger_repo.entries(sqlite_trip.group_id) == []
