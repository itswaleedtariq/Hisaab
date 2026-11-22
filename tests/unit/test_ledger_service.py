"""LedgerService: events become append-only ledger entries. Owner: Abdullah Rashid."""

from datetime import UTC, date, datetime

from hisaab.domain.clock import FixedClock
from hisaab.domain.models import Expense, LedgerSource, Settlement, Share, SplitType
from hisaab.domain.money import Money
from hisaab.events.bus import EventBus
from hisaab.events.events import ExpenseRecorded, ExpenseVoided, SettlementRecorded
from hisaab.ledger.repository import InMemoryLedgerRepository
from hisaab.ledger.service import LedgerService

NOW = datetime(2026, 11, 15, tzinfo=UTC)


def setup():
    ledger, bus = InMemoryLedgerRepository(), EventBus()
    LedgerService(ledger, FixedClock(NOW)).subscribe_to(bus)
    return ledger, bus


def expense(payer=1, shares=((1, 300), (2, 300), (3, 300)), eid=7):
    return Expense(
        id=eid, group_id=5, payer_id=payer, amount=Money(sum(p for _, p in shares)),
        split_type=SplitType.EQUAL, shares=tuple(Share(u, Money(p)) for u, p in shares),
        spent_on=date(2026, 11, 1), created_by=payer, created_at=NOW,
    )


def test_expense_becomes_net_entries_per_member():
    ledger, bus = setup()
    bus.publish(ExpenseRecorded(expense()))
    assert ledger.balances(5) == {1: Money(600), 2: Money(-300), 3: Money(-300)}
    assert {e.source_type for e in ledger.entries(5)} == {LedgerSource.EXPENSE}


def test_payer_outside_split_and_zero_net_rows_are_skipped():
    ledger, bus = setup()
    bus.publish(ExpenseRecorded(expense(payer=1, shares=((1, 0), (2, 500)))))
    assert ledger.balances(5) == {1: Money(500), 2: Money(-500)}
    assert len(ledger.entries(5)) == 2  # user 1's zero share produced no extra row


def test_void_appends_reversals_and_keeps_originals():
    ledger, bus = setup()
    e = expense()
    bus.publish(ExpenseRecorded(e))
    bus.publish(ExpenseVoided(e, voided_by=1))
    assert all(b.is_zero() for b in ledger.balances(5).values())
    assert [x.source_type for x in ledger.entries(5)].count(LedgerSource.VOID) == 3


def test_void_only_reverses_its_own_expense():
    ledger, bus = setup()
    bus.publish(ExpenseRecorded(expense(eid=1)))
    bus.publish(ExpenseRecorded(expense(eid=2)))
    bus.publish(ExpenseVoided(expense(eid=1), voided_by=1))
    assert ledger.balances(5) == {1: Money(600), 2: Money(-300), 3: Money(-300)}


def test_settlement_moves_balance_between_two_members():
    ledger, bus = setup()
    bus.publish(ExpenseRecorded(expense()))
    bus.publish(SettlementRecorded(Settlement(9, 5, 2, 1, Money(300), NOW)))
    assert ledger.balances(5) == {1: Money(300), 2: Money(0), 3: Money(-300)}
