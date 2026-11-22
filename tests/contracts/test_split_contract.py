"""LSP contract: every SplitStrategy behaves the same way to its callers.

Includes the QR-01 property test. Run with HYPOTHESIS_PROFILE=thorough for the
full 10,000 examples per split type; CI uses the default (300) to stay fast.
"""

import os

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hisaab.domain.errors import InvalidSplitError
from hisaab.domain.money import MAX_EXPENSE_PAISA, Money
from hisaab.splitting.strategies import (
    EqualSplit,
    ExactSplit,
    PercentageSplit,
    ShareSplit,
    SplitStrategy,
)

settings.register_profile("default", max_examples=300, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("thorough", max_examples=10_000, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))


def make_strategy(kind: str, total: Money, people: list[int], draw) -> SplitStrategy:
    if kind == "equal":
        return EqualSplit()
    if kind == "exact":
        parts = total.allocate([draw(st.integers(1, 100)) for _ in people])
        return ExactSplit(dict(zip(people, parts, strict=True)))
    if kind == "percent":
        bps = Money(10_000).allocate([draw(st.integers(1, 100)) for _ in people])
        if any(b.paisa == 0 for b in bps):
            bps = Money(10_000).allocate([1] * len(people))
        return PercentageSplit(
            {p: f"{b.paisa // 100}.{b.paisa % 100:02d}" for p, b in zip(people, bps, strict=True)}
        )
    return ShareSplit({p: draw(st.integers(1, 20)) for p in people})


KINDS = ["equal", "exact", "percent", "shares"]


@pytest.mark.parametrize("kind", KINDS)
@given(data=st.data())
def test_qr01_shares_always_sum_to_total(kind, data):
    total = Money(data.draw(st.integers(1, MAX_EXPENSE_PAISA)))
    people = data.draw(st.lists(st.integers(1, 10_000), min_size=1, max_size=12, unique=True))
    payer = data.draw(st.sampled_from(people))
    strategy = make_strategy(kind, total, people, data.draw)
    shares = strategy.split(total, people, payer)
    assert [s.user_id for s in shares] == people  # one share per participant, in order
    assert all(s.amount.paisa >= 0 for s in shares)
    assert sum(s.amount.paisa for s in shares) == total.paisa


@pytest.mark.parametrize(
    "strategy",
    [EqualSplit(), ExactSplit({1: Money(0)}), PercentageSplit({1: "100"}), ShareSplit({1: 1})],
    ids=KINDS,
)
def test_every_strategy_rejects_bad_input_the_same_way(strategy):
    for total, people in [(Money(0), [1]), (Money(10), []), (Money(10), [1, 1])]:
        with pytest.raises(InvalidSplitError):
            strategy.split(total, people, 1)
