from decimal import Decimal

import pytest

from hisaab.domain.errors import InvalidAmountError
from hisaab.domain.money import Money


def test_from_rupees_converts_to_paisa():
    assert Money.from_rupees("1250.50") == Money(125050)
    assert Money.from_rupees(10) == Money(1000)
    assert Money.from_rupees(Decimal("0.01")) == Money(1)


@pytest.mark.parametrize("bad", ["10.005", "abc", "NaN", "Infinity", ""])
def test_from_rupees_rejects_bad_input(bad):
    with pytest.raises(InvalidAmountError):
        Money.from_rupees(bad)


@pytest.mark.parametrize("bad", [1.5, "100", True])
def test_money_only_accepts_int_paisa(bad):
    with pytest.raises(InvalidAmountError):
        Money(bad)


def test_arithmetic_and_formatting():
    a, b = Money(150), Money(275)
    assert (a + b).paisa == 425
    assert (a - b).to_rupees_str() == "-1.25"
    assert (-a).paisa == -150
    assert Money.zero().is_zero()
    assert Money(5).to_rupees_str() == "0.05"


def test_allocate_parts_always_sum_to_total():
    parts = Money(100).allocate([1, 1, 1])
    assert [p.paisa for p in parts] == [34, 33, 33]
    assert sum(p.paisa for p in parts) == 100


def test_allocate_gives_leftover_to_largest_remainder_then_earliest():
    # 1000 split 1:2 -> 333.33 / 666.66 -> remainders tie-broken by position
    parts = Money(1000).allocate([1, 2])
    assert [p.paisa for p in parts] == [333, 667]


@pytest.mark.parametrize(
    "weights", [[], [1, -1], [0, 0]], ids=["empty", "negative", "all-zero"]
)
def test_allocate_rejects_bad_weights(weights):
    with pytest.raises(InvalidAmountError):
        Money(100).allocate(weights)


def test_allocate_rejects_negative_amount():
    with pytest.raises(InvalidAmountError):
        Money(-1).allocate([1])
