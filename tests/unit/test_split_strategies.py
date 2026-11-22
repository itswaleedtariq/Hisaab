"""Black-box tests for the Split Engine (FR-05 to FR-08).

Test case ids (TC-BB-xx) match the black-box design in the SE431 M2 report.
"""

import pytest

from hisaab.domain.errors import InvalidSplitError
from hisaab.domain.money import Money
from hisaab.splitting.strategies import (
    EqualSplit,
    ExactSplit,
    PercentageSplit,
    ShareSplit,
)

A, B, C = 1, 2, 3


def amounts(shares):
    return [s.amount.paisa for s in shares]


# --- FR-05 equal split: BVA on the remainder (total mod n) ------------------
@pytest.mark.parametrize(
    ("total", "payer", "expected"),
    [
        pytest.param(99, A, [33, 33, 33], id="TC-BB-20 remainder 0"),
        pytest.param(100, A, [34, 33, 33], id="TC-BB-21 remainder 1 goes to payer"),
        pytest.param(101, A, [34, 34, 33], id="TC-BB-22 remainder n-1"),
        pytest.param(100, B, [33, 34, 33], id="TC-BB-23 payer not first in list"),
        pytest.param(1, C, [0, 0, 1], id="TC-BB-24 one paisa, three people"),
    ],
)
def test_equal_split_remainders(total, payer, expected):
    assert amounts(EqualSplit().split(Money(total), [A, B, C], payer)) == expected


def test_equal_split_payer_not_participant_leftover_to_first():
    assert amounts(EqualSplit().split(Money(100), [B, C], A)) == [50, 50]
    assert amounts(EqualSplit().split(Money(101), [B, C], A)) == [51, 50]


# --- FR-06 exact split: EP on the sum ---------------------------------------
@pytest.mark.parametrize(
    ("given", "ok"),
    [
        pytest.param({A: 400, B: 500}, False, id="TC-BB-25 sum below total"),
        pytest.param({A: 400, B: 600}, True, id="TC-BB-26 sum equals total"),
        pytest.param({A: 400, B: 601}, False, id="TC-BB-27 sum above total"),
    ],
)
def test_exact_split_sum_classes(given, ok):
    strategy = ExactSplit({uid: Money(p) for uid, p in given.items()})
    if ok:
        assert amounts(strategy.split(Money(1000), [A, B], A)) == [400, 600]
    else:
        with pytest.raises(InvalidSplitError):
            strategy.split(Money(1000), [A, B], A)


def test_exact_split_rejects_missing_or_extra_people_and_negatives():
    with pytest.raises(InvalidSplitError):
        ExactSplit({A: Money(1000)}).split(Money(1000), [A, B], A)
    with pytest.raises(InvalidSplitError):
        ExactSplit({A: Money(1100), B: Money(-100)}).split(Money(1000), [A, B], A)


# --- FR-07 percentage split: BVA on the total and on each value ---------------
@pytest.mark.parametrize(
    ("pcts", "ok"),
    [
        pytest.param({A: "50", B: "49.99"}, False, id="TC-BB-28 total 99.99"),
        pytest.param({A: "50", B: "50.00"}, True, id="TC-BB-29 total 100.00"),
        pytest.param({A: "50", B: "50.01"}, False, id="TC-BB-30 total 100.01"),
    ],
)
def test_percentage_total_boundaries(pcts, ok):
    if ok:
        shares = PercentageSplit(pcts).split(Money(1000), [A, B], A)
        assert amounts(shares) == [500, 500]
    else:
        with pytest.raises(InvalidSplitError):
            PercentageSplit(pcts).split(Money(1000), [A, B], A)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("0", id="TC-BB-31 zero percent"),
        pytest.param("100.01", id="TC-BB-32 above 100"),
        pytest.param("33.333", id="TC-BB-33 three decimals"),
        pytest.param("abc", id="TC-BB-34 not a number"),
        pytest.param("-5", id="negative"),
        pytest.param("NaN", id="nan"),
    ],
)
def test_percentage_value_rejected(value):
    with pytest.raises(InvalidSplitError):
        PercentageSplit({A: value, B: "50"})


def test_percentage_smallest_and_largest_valid_values():
    shares = PercentageSplit({A: "0.01", B: "99.99"}).split(Money(10000), [A, B], A)
    assert amounts(shares) == [1, 9999]
    assert amounts(PercentageSplit({A: "100"}).split(Money(777), [A], A)) == [777]


def test_percentage_rounding_still_sums_to_total():
    shares = PercentageSplit({A: "33.33", B: "33.33", C: "33.34"}).split(Money(100), [A, B, C], A)
    assert sum(amounts(shares)) == 100


def test_percentage_requires_one_value_per_participant():
    with pytest.raises(InvalidSplitError):
        PercentageSplit({A: "100"}).split(Money(100), [A, B], A)


# --- FR-08 shares split: BVA on share values ------------------------------
@pytest.mark.parametrize(
    ("value", "ok"),
    [
        pytest.param(0, False, id="TC-BB-35 share 0"),
        pytest.param(1, True, id="TC-BB-36 share 1"),
        pytest.param(-1, False, id="TC-BB-37 negative share"),
        pytest.param(1.5, False, id="TC-BB-38 fractional share"),
    ],
)
def test_share_values(value, ok):
    strategy = ShareSplit({A: value, B: 1})
    if ok:
        assert amounts(strategy.split(Money(1000), [A, B], A)) == [500, 500]
    else:
        with pytest.raises(InvalidSplitError):
            strategy.split(Money(1000), [A, B], A)


def test_shares_two_to_one():
    assert amounts(ShareSplit({A: 2, B: 1, C: 1}).split(Money(1000), [A, B, C], A)) == [
        500,
        250,
        250,
    ]


def test_share_split_requires_matching_people():
    with pytest.raises(InvalidSplitError):
        ShareSplit({A: 1}).split(Money(100), [A, B], A)


# --- checks common to every strategy (template method) ---------------------
@pytest.mark.parametrize(
    ("total", "participants"),
    [
        (Money(0), [A]),
        (Money(100), []),
        (Money(100), [A, A]),
        (Money(100), list(range(1, 52))),
    ],
    ids=["zero total", "no participants", "duplicate participant", "51 participants"],
)
def test_common_input_checks(total, participants):
    with pytest.raises(InvalidSplitError):
        EqualSplit().split(total, participants, A)


# --- PercentageSplit._to_basis_points: basis paths (SE431 M2 white-box design) --
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("abc", None, id="TC-WB-05 Decimal() raises"),
        pytest.param("NaN", None, id="TC-WB-06 not finite"),
        pytest.param("33.333", None, id="TC-WB-07 more than 2 decimals"),
        pytest.param("0", None, id="TC-WB-08 pct <= 0"),
        pytest.param("100.01", None, id="TC-WB-09 pct > 100"),
        pytest.param("12.5", 1250, id="TC-WB-10 valid value"),
    ],
)
def test_to_basis_points_basis_paths(value, expected):
    if expected is None:
        with pytest.raises(InvalidSplitError):
            PercentageSplit._to_basis_points(value)
    else:
        assert PercentageSplit._to_basis_points(value) == expected
