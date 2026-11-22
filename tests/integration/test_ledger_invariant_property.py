"""QR-02: balances of a group always sum to zero after any sequence of
expenses, voids and settlements (property-based, Hypothesis)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from hisaab.bootstrap import build_in_memory
from hisaab.domain.clock import FixedClock
from hisaab.domain.errors import HisaabError
from hisaab.domain.money import Money
from hisaab.expenses.service import NewExpense
from tests.conftest import NOW, make_trip

ops = st.lists(
    st.one_of(
        st.tuples(st.just("spend"), st.integers(0, 2), st.integers(1, 5_000_000)),
        st.tuples(st.just("void"), st.integers(0, 50), st.just(0)),
        st.tuples(st.just("settle"), st.integers(0, 2), st.integers(1, 5_000_000)),
    ),
    max_size=25,
)


@settings(max_examples=100, deadline=None)
@given(ops)
def test_qr02_balances_always_sum_to_zero(operations):
    c = build_in_memory(clock=FixedClock(NOW))
    trip = make_trip(c)
    people = [trip.ali, trip.sara, trip.bilal]
    recorded = []
    try:
        for kind, who, amount in operations:
            try:
                if kind == "spend":
                    e = c.expenses.record(
                        NewExpense(trip.group_id, people[who], Money(amount), "equal", people),
                        people[who],
                    )
                    recorded.append(e.id)
                elif kind == "void" and recorded:
                    c.expenses.void(recorded[who % len(recorded)], trip.ali)
                elif kind == "settle":
                    plan = c.settlement.suggest_plan(trip.group_id, trip.ali)
                    if plan:
                        t = plan[0]
                        pay = Money(min(amount, t.amount.paisa))
                        c.settlement.record_payment(
                            trip.group_id, trip.ali, t.from_user_id, t.to_user_id, pay
                        )
            except HisaabError:
                pass  # rejected operations must not break the invariant either
            total = sum(b.paisa for b in c.ledger_repo.balances(trip.group_id).values())
            assert total == 0
    finally:
        c.close()
