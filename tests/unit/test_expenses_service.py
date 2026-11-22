"""ExpenseService (FR-04, FR-09, FR-16). Owner: Muhammad Abdullah."""

import pytest

from hisaab.domain.errors import (
    ConflictError,
    ExpenseAlreadyVoidedError,
    ExpenseNotFoundError,
    GroupTooSmallError,
    InvalidSplitError,
    NotGroupAdminError,
    NotGroupMemberError,
)
from hisaab.domain.models import ExpenseStatus
from hisaab.domain.money import Money
from hisaab.events.bus import EventBus
from hisaab.events.events import ExpenseRecorded
from hisaab.expenses.repository import InMemoryExpenseRepository
from hisaab.expenses.service import ExpenseService, NewExpense
from hisaab.ledger.service import LedgerService
from hisaab.splitting.factory import default_factory


@pytest.fixture
def g(people):
    """people + an ExpenseService whose events feed a real LedgerService."""
    bus = EventBus()
    LedgerService(people.ledger, people.clock).subscribe_to(bus)
    people.bus = bus
    people.expenses = ExpenseService(
        InMemoryExpenseRepository(), people.groups, default_factory(), bus, people.uow,
        people.clock,
    )

    def spend(payer, rupees, participants=None, split="equal", key=None, **params):
        return people.expenses.record(
            NewExpense(people.group_id, payer, Money.from_rupees(rupees), split,
                       participants or [people.ali, people.sara, people.bilal],
                       params, idempotency_key=key),
            payer,
        )

    people.spend = spend
    return people


def test_record_equal_expense_updates_balances(g):
    expense = g.spend(g.ali, "300")
    assert expense.id is not None
    assert g.ledger.balances(g.group_id) == {
        g.ali: Money(20000), g.sara: Money(-10000), g.bilal: Money(-10000)
    }


def test_record_publishes_expense_recorded(g):
    seen = []
    g.bus.subscribe(ExpenseRecorded, seen.append)
    expense = g.spend(g.sara, "90")
    assert [e.expense.id for e in seen] == [expense.id]


def test_each_split_type_through_the_service(g):
    a, s, b = g.ali, g.sara, g.bilal
    exact = g.spend(a, "100", [a, s], split="exact", amounts={a: "30", s: "70"})
    pct = g.spend(a, "100", [a, s], split="percent", percentages={a: "25", s: "75"})
    shares = g.spend(a, "100", [a, s, b], split="shares", shares={a: 2, s: 1, b: 1})
    assert [x.amount.paisa for x in exact.shares] == [3000, 7000]
    assert [x.amount.paisa for x in pct.shares] == [2500, 7500]
    assert [x.amount.paisa for x in shares.shares] == [5000, 2500, 2500]


def test_unknown_split_type(g):
    with pytest.raises(InvalidSplitError):
        g.spend(g.ali, "100", split="by_income")


@pytest.mark.parametrize(
    "who",
    [pytest.param("payer", id="TC-BB-19a payer not a member"),
     pytest.param("participant", id="TC-BB-19b participant not a member")],
)
def test_payer_and_participants_must_be_members(g, who):
    zara = g.users.register("Zara", "zara@example.com").id
    payer = zara if who == "payer" else g.ali
    participants = [g.ali, g.sara] if who == "payer" else [g.ali, zara]
    with pytest.raises(NotGroupMemberError):
        g.expenses.record(NewExpense(g.group_id, payer, Money(1000), "equal", participants), g.ali)


def test_actor_must_be_member(g):
    zara = g.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        g.expenses.record(NewExpense(g.group_id, g.ali, Money(1000), "equal", [g.ali]), zara)


def test_group_needs_two_members(g):
    solo = g.groups.create_group("Solo", g.ali)
    with pytest.raises(GroupTooSmallError):
        g.expenses.record(NewExpense(solo.id, g.ali, Money(100), "equal", [g.ali]), g.ali)


# --- FR-16 idempotency --------------------------------------------------------
def test_repeated_idempotency_key_returns_first_result(g):
    first = g.spend(g.ali, "9", key="k-123")
    second = g.spend(g.ali, "9", key="k-123")
    assert first.id == second.id
    assert len(g.expenses.list_for_group(g.group_id, g.ali)) == 1
    assert g.ledger.balance_of(g.group_id, g.ali) == Money(600)


def test_idempotency_key_reused_in_other_group_conflicts(g):
    other = g.groups.create_group("Office", g.ali)
    g.groups.add_member(other.id, g.ali, g.sara)
    g.spend(g.ali, "1", key="k")
    with pytest.raises(ConflictError):
        g.expenses.record(
            NewExpense(other.id, g.ali, Money(100), "equal", [g.ali], idempotency_key="k"), g.ali
        )


# --- FR-09 void ---------------------------------------------------------------
def test_void_reverses_ledger_and_keeps_history(g):
    expense = g.spend(g.sara, "300")
    voided = g.expenses.void(expense.id, g.sara)
    assert voided.status is ExpenseStatus.VOIDED
    assert all(b.is_zero() for b in g.ledger.balances(g.group_id).values())
    sources = [e.source_type.value for e in g.ledger.entries(g.group_id)]
    assert sources.count("expense") == 3 and sources.count("void") == 3


def test_admin_can_void_others_expense(g):
    expense = g.spend(g.sara, "300")
    assert g.expenses.void(expense.id, g.ali).status is ExpenseStatus.VOIDED


@pytest.mark.parametrize(
    "case",
    [pytest.param("other member", id="TC-BB-39 neither admin nor creator"),
     pytest.param("twice", id="TC-BB-40 already voided"),
     pytest.param("missing", id="TC-BB-41 unknown expense")],
)
def test_void_errors(g, case):
    expense = g.spend(g.sara, "300")
    if case == "other member":
        with pytest.raises(NotGroupAdminError):
            g.expenses.void(expense.id, g.bilal)
    elif case == "twice":
        g.expenses.void(expense.id, g.sara)
        with pytest.raises(ExpenseAlreadyVoidedError):
            g.expenses.void(expense.id, g.sara)
    else:
        with pytest.raises(ExpenseNotFoundError):
            g.expenses.void(999, g.sara)


def test_get_and_list_require_membership(g):
    expense = g.spend(g.ali, "50")
    assert g.expenses.get(expense.id, g.bilal) == expense
    zara = g.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        g.expenses.get(expense.id, zara)
    with pytest.raises(NotGroupMemberError):
        g.expenses.list_for_group(g.group_id, zara)


def test_idempotent_replay_still_requires_membership(g):
    """DEF-01: a reused key must not let a non-member read another group's expense."""
    g.spend(g.ali, "9", key="k-secret")
    zara = g.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        g.expenses.record(
            NewExpense(g.group_id, zara, Money(900), "equal", [zara], idempotency_key="k-secret"),
            zara,
        )
