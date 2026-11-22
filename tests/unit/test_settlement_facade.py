"""SettlementFacade (FR-10 to FR-12). Owner: Abdullah Rashid."""

import pytest

from hisaab.domain.errors import (
    InvalidSettlementError,
    NotGroupAdminError,
    NotGroupMemberError,
)
from hisaab.domain.models import LedgerEntry, LedgerSource
from hisaab.domain.money import Money
from hisaab.events.bus import EventBus
from hisaab.ledger.facade import SettlementFacade
from hisaab.ledger.planner import SettlementPlanner
from hisaab.ledger.repository import InMemorySettlementRepository
from hisaab.ledger.service import LedgerService
from tests.conftest import NOW


@pytest.fixture
def f(people):
    bus = EventBus()
    LedgerService(people.ledger, people.clock).subscribe_to(bus)
    people.settlements = InMemorySettlementRepository()
    people.facade = SettlementFacade(
        people.ledger, SettlementPlanner(), people.settlements, bus, people.groups,
        people.uow, people.clock,
    )

    def owes(debtor, creditor, paisa):
        people.ledger.append([
            LedgerEntry(people.group_id, creditor, Money(paisa), LedgerSource.EXPENSE, 1, NOW),
            LedgerEntry(people.group_id, debtor, Money(-paisa), LedgerSource.EXPENSE, 1, NOW),
        ])

    people.owes = owes
    return people


# --- FR-10 balances -------------------------------------------------------------
def test_balances_include_members_at_zero(f):
    f.owes(f.bilal, f.ali, 500)
    assert f.facade.balances(f.group_id, f.sara) == {
        f.ali: Money(500), f.sara: Money(0), f.bilal: Money(-500)
    }


def test_non_member_cannot_see_balances_or_plan(f):
    zara = f.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        f.facade.balances(f.group_id, zara)
    with pytest.raises(NotGroupMemberError):
        f.facade.suggest_plan(f.group_id, zara)


# --- FR-11 suggest --------------------------------------------------------------
def test_suggested_plan_is_not_stored(f):
    f.owes(f.bilal, f.ali, 10000)
    f.owes(f.sara, f.ali, 5000)
    plan = f.facade.suggest_plan(f.group_id, f.bilal)
    assert len(plan) == 2
    assert f.settlements.list_for_group(f.group_id) == []


# --- FR-12 record payment: BVA on amount vs debt (debt = PKR 100.00) ---------------
@pytest.mark.parametrize(
    ("rupees", "ok"),
    [
        pytest.param("0", False, id="TC-BB-42 amount 0.00"),
        pytest.param("0.01", True, id="TC-BB-43 amount 0.01"),
        pytest.param("100.00", True, id="TC-BB-44 amount equals debt"),
        pytest.param("100.01", False, id="TC-BB-45 amount above debt"),
    ],
)
def test_payment_amount_boundaries(f, rupees, ok):
    f.owes(f.bilal, f.ali, 10000)
    pay = Money.from_rupees(rupees)
    if ok:
        s = f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.ali, pay)
        assert s.amount == pay
        assert f.ledger.balance_of(f.group_id, f.bilal) == Money(-10000 + pay.paisa)
    else:
        with pytest.raises(InvalidSettlementError):
            f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.ali, pay)


def test_payment_rules(f):
    f.owes(f.bilal, f.ali, 10000)
    g, a, s, b = f.group_id, f.ali, f.sara, f.bilal
    with pytest.raises(NotGroupAdminError):  # sara records bilal's payment
        f.facade.record_payment(g, s, b, a, Money(100))
    with pytest.raises(InvalidSettlementError):  # pay yourself
        f.facade.record_payment(g, b, b, b, Money(100))
    with pytest.raises(InvalidSettlementError):  # a creditor cannot "pay" a debtor
        f.facade.record_payment(g, a, a, b, Money(100))
    zara = f.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        f.facade.record_payment(g, a, b, zara, Money(100))
    f.facade.record_payment(g, a, b, a, Money(100))  # admin records on bilal's behalf
    assert len(f.settlements.list_for_group(g)) == 1


def test_settle_up_is_admin_only_and_clears_every_balance(f):
    f.owes(f.bilal, f.ali, 10000)
    f.owes(f.sara, f.bilal, 2500)
    with pytest.raises(NotGroupAdminError):
        f.facade.settle_up(f.group_id, f.sara)
    plan = f.facade.settle_up(f.group_id, f.ali)
    assert 1 <= len(plan) <= 2
    assert all(b.is_zero() for b in f.facade.balances(f.group_id, f.ali).values())


# --- record_payment: basis paths (SE431 M2 white-box design) ---------------------
def test_tc_wb_11_actor_neither_payer_nor_admin(f):
    f.owes(f.bilal, f.ali, 10000)
    with pytest.raises(NotGroupAdminError):
        f.facade.record_payment(f.group_id, f.sara, f.bilal, f.ali, Money(100))


def test_tc_wb_12_payer_not_a_member(f):
    zara = f.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        f.facade.record_payment(f.group_id, f.ali, zara, f.ali, Money(100))


def test_tc_wb_13_receiver_not_a_member(f):
    zara = f.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        f.facade.record_payment(f.group_id, f.bilal, f.bilal, zara, Money(100))


def test_tc_wb_14_paying_yourself(f):
    with pytest.raises(InvalidSettlementError, match="to_user_id"):
        f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.bilal, Money(100))


def test_tc_wb_15_amount_not_positive(f):
    f.owes(f.bilal, f.ali, 10000)
    with pytest.raises(InvalidSettlementError, match="greater than 0"):
        f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.ali, Money(0))


def test_tc_wb_16_amount_above_what_is_owed(f):
    f.owes(f.bilal, f.ali, 10000)
    with pytest.raises(InvalidSettlementError, match="exceed"):
        f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.ali, Money(10001))


def test_tc_wb_17_valid_payment_is_stored(f):
    f.owes(f.bilal, f.ali, 10000)
    s = f.facade.record_payment(f.group_id, f.bilal, f.bilal, f.ali, Money(4000))
    assert (s.from_user_id, s.to_user_id, s.amount) == (f.bilal, f.ali, Money(4000))
    assert f.ledger.balance_of(f.group_id, f.bilal) == Money(-6000)
