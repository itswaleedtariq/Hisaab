"""SplitStrategyFactory (registry-based Factory). Owner: Muhammad Abdullah."""

import pytest

from hisaab.domain.errors import InvalidAmountError, InvalidSplitError
from hisaab.domain.money import Money
from hisaab.splitting.factory import default_factory
from hisaab.splitting.strategies import EqualSplit, ExactSplit, PercentageSplit, ShareSplit

A, B, C = 1, 2, 3


def amounts(shares):
    return [s.amount.paisa for s in shares]


# --- Factory ----------------------------------------------------------------
def test_factory_builds_each_registered_type():
    f = default_factory()
    assert f.supported() == ["equal", "exact", "percent", "shares"]
    assert isinstance(f.create("equal"), EqualSplit)
    assert isinstance(f.create("exact", {"amounts": {"1": "5.00"}}), ExactSplit)
    assert isinstance(f.create("percent", {"percentages": {1: "100"}}), PercentageSplit)
    assert isinstance(f.create("shares", {"shares": {1: 1}}), ShareSplit)


def test_factory_rejects_unknown_type_and_missing_params():
    f = default_factory()
    with pytest.raises(InvalidSplitError, match="split_type"):
        f.create("by_income")
    with pytest.raises(InvalidSplitError, match="amounts"):
        f.create("exact", {})
    with pytest.raises(InvalidSplitError, match="keys must be user ids"):
        f.create("shares", {"shares": {"ali": 1}})
    with pytest.raises(InvalidAmountError):
        f.create("exact", {"amounts": {"1": "1.234"}})


def test_factory_is_open_for_extension():
    """QR-15: a new split type is one register() call; nothing else changes."""

    class PayerPaysAll(EqualSplit):
        def _split(self, total, participants, payer_id):
            return self._allocate(
                total, participants, payer_id, {p: int(p == payer_id) for p in participants}
            )

    f = default_factory()
    f.register("payer_only", lambda _p: PayerPaysAll())
    assert amounts(f.create("payer_only").split(Money(900), [A, B, C], A)) == [900, 0, 0]
