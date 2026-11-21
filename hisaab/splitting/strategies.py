"""Strategy pattern: the four ways of dividing an expense (FR-05 to FR-08).

Contract every SplitStrategy must honour (checked by tests/contracts):
  * return exactly one Share per participant, in participant order;
  * shares are never negative and add up exactly to the total;
  * on bad input raise InvalidSplitError and return nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation

from hisaab.domain.errors import InvalidSplitError
from hisaab.domain.models import Share
from hisaab.domain.money import Money

MAX_PARTICIPANTS = 50


def _payer_first(participants: list[int], payer_id: int) -> list[int]:
    """Order used for leftover paisa: payer first, then the others as given."""
    if payer_id in participants:
        return [payer_id] + [p for p in participants if p != payer_id]
    return list(participants)


class SplitStrategy(ABC):
    def split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]:
        """Template method: common checks, then the strategy-specific weights."""
        if total.paisa <= 0:
            raise InvalidSplitError("amount", "must be greater than 0")
        if not participants:
            raise InvalidSplitError("participants", "at least one participant is required")
        if len(set(participants)) != len(participants):
            raise InvalidSplitError("participants", "a participant is listed twice")
        if len(participants) > MAX_PARTICIPANTS:
            raise InvalidSplitError("participants", f"at most {MAX_PARTICIPANTS} allowed")
        return self._split(total, participants, payer_id)

    @abstractmethod
    def _split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]: ...

    @staticmethod
    def _allocate(
        total: Money, participants: list[int], payer_id: int, weights: dict[int, int]
    ) -> list[Share]:
        order = _payer_first(participants, payer_id)
        parts = total.allocate([weights[uid] for uid in order])
        by_user = dict(zip(order, parts, strict=True))
        return [Share(uid, by_user[uid]) for uid in participants]


class EqualSplit(SplitStrategy):
    """FR-05: everyone pays the same; leftover paisa go to the payer first."""

    def _split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]:
        return self._allocate(total, participants, payer_id, {p: 1 for p in participants})


class ExactSplit(SplitStrategy):
    """FR-06: the payer types each member's amount; they must add up to the total."""

    def __init__(self, amounts: dict[int, Money]) -> None:
        self._amounts = dict(amounts)

    def _split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]:
        if set(self._amounts) != set(participants):
            raise InvalidSplitError("amounts", "must give exactly one amount per participant")
        if any(a.paisa < 0 for a in self._amounts.values()):
            raise InvalidSplitError("amounts", "an amount cannot be negative")
        given = sum(a.paisa for a in self._amounts.values())
        if given != total.paisa:
            raise InvalidSplitError(
                "amounts", f"must add up to the total ({given} != {total.paisa} paisa)"
            )
        return [Share(uid, self._amounts[uid]) for uid in participants]


class PercentageSplit(SplitStrategy):
    """FR-07: percentages with at most 2 decimals that total exactly 100.00."""

    def __init__(self, percentages: dict[int, str | Decimal]) -> None:
        self._basis_points = {uid: self._to_basis_points(v) for uid, v in percentages.items()}

    @staticmethod
    def _to_basis_points(value: str | Decimal) -> int:
        try:
            pct = Decimal(str(value))
        except InvalidOperation as exc:
            raise InvalidSplitError("percentages", "must be numbers") from exc
        if not pct.is_finite():
            raise InvalidSplitError("percentages", "must be numbers")
        if pct.as_tuple().exponent < -2:  # type: ignore[operator]
            raise InvalidSplitError("percentages", "at most 2 decimal places")
        if pct <= 0 or pct > 100:
            raise InvalidSplitError("percentages", "each must be above 0 and at most 100")
        return int(pct * 100)

    def _split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]:
        if set(self._basis_points) != set(participants):
            raise InvalidSplitError("percentages", "must give one percentage per participant")
        if sum(self._basis_points.values()) != 10_000:
            raise InvalidSplitError("percentages", "must total exactly 100.00")
        return self._allocate(total, participants, payer_id, self._basis_points)


class ShareSplit(SplitStrategy):
    """FR-08: split by positive integer shares, e.g. 2:1:1."""

    def __init__(self, shares: dict[int, int]) -> None:
        self._shares = dict(shares)

    def _split(self, total: Money, participants: list[int], payer_id: int) -> list[Share]:
        if set(self._shares) != set(participants):
            raise InvalidSplitError("shares", "must give one share count per participant")
        for count in self._shares.values():
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise InvalidSplitError("shares", "each share must be a whole number of 1 or more")
        return self._allocate(total, participants, payer_id, self._shares)
