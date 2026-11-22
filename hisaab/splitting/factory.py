"""Registry-based Factory: turns a split type string into a SplitStrategy.

Adding a new split type means one new SplitStrategy subclass and one
``register`` call. ExpenseService and the API do not change (OCP, QR-15).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hisaab.domain.errors import InvalidSplitError
from hisaab.domain.money import Money
from hisaab.splitting.strategies import (
    EqualSplit,
    ExactSplit,
    PercentageSplit,
    ShareSplit,
    SplitStrategy,
)

Creator = Callable[[Mapping[str, Any]], SplitStrategy]


def _user_map(params: Mapping[str, Any], key: str) -> dict[int, Any]:
    raw = params.get(key)
    if not isinstance(raw, Mapping) or not raw:
        raise InvalidSplitError(key, "is required for this split type")
    try:
        return {int(uid): value for uid, value in raw.items()}
    except (TypeError, ValueError) as exc:
        raise InvalidSplitError(key, "keys must be user ids") from exc


def _exact(params: Mapping[str, Any]) -> SplitStrategy:
    amounts = _user_map(params, "amounts")
    return ExactSplit({uid: Money.from_rupees(v) for uid, v in amounts.items()})


def _percent(params: Mapping[str, Any]) -> SplitStrategy:
    return PercentageSplit(_user_map(params, "percentages"))


def _shares(params: Mapping[str, Any]) -> SplitStrategy:
    return ShareSplit(_user_map(params, "shares"))


class SplitStrategyFactory:
    def __init__(self) -> None:
        self._creators: dict[str, Creator] = {}

    def register(self, split_type: str, creator: Creator) -> None:
        self._creators[split_type] = creator

    def supported(self) -> list[str]:
        return sorted(self._creators)

    def create(self, split_type: str, params: Mapping[str, Any] | None = None) -> SplitStrategy:
        creator = self._creators.get(split_type)
        if creator is None:
            raise InvalidSplitError(
                "split_type", f"must be one of {', '.join(self.supported())}"
            )
        return creator(params or {})


def default_factory() -> SplitStrategyFactory:
    factory = SplitStrategyFactory()
    factory.register("equal", lambda _params: EqualSplit())
    factory.register("exact", _exact)
    factory.register("percent", _percent)
    factory.register("shares", _shares)
    return factory
