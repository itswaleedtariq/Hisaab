"""SettlementPlanner (FR-11). Owner: Abdullah Rashid.

These tests cover every branch of plan(); they also guarded the SA-01 refactor.
"""

import pytest

from hisaab.domain.errors import InvalidSettlementError
from hisaab.domain.money import Money
from hisaab.ledger.planner import SettlementPlanner

P = SettlementPlanner()


def m(**balances):
    return {int(k[1:]): Money(v) for k, v in balances.items()}


def test_unbalanced_input_rejected():
    with pytest.raises(InvalidSettlementError):
        P.plan(m(u1=100, u2=-50))


def test_everyone_at_zero_gives_no_transfers():
    assert P.plan(m(u1=0, u2=0)) == []
    assert P.plan({}) == []


def test_one_debtor_one_creditor_exact_match():
    [t] = P.plan(m(u1=500, u2=-500))
    assert (t.from_user_id, t.to_user_id, t.amount.paisa) == (2, 1, 500)


def test_creditor_left_with_remainder():
    plan = P.plan(m(u1=900, u2=-500, u3=-400))
    assert [(t.from_user_id, t.to_user_id, t.amount.paisa) for t in plan] == [
        (2, 1, 500),
        (3, 1, 400),
    ]


def test_debtor_left_with_remainder():
    plan = P.plan(m(u1=500, u2=400, u3=-900))
    assert [(t.from_user_id, t.to_user_id, t.amount.paisa) for t in plan] == [
        (3, 1, 500),
        (3, 2, 400),
    ]


def test_plan_never_exceeds_n_minus_1():
    balances = m(u1=1000, u2=-300, u3=-300, u4=-250, u5=-150)
    plan = P.plan(balances)
    assert len(plan) <= 4
    final = {uid: b.paisa for uid, b in balances.items()}
    for t in plan:
        final[t.from_user_id] += t.amount.paisa
        final[t.to_user_id] -= t.amount.paisa
    assert set(final.values()) == {0}
