"""Money as integer paisa. Floats are never used for amounts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from hisaab.domain.errors import InvalidAmountError

PAISA_PER_RUPEE = 100
MAX_EXPENSE_PAISA = 1_000_000_000  # PKR 10,000,000


@dataclass(frozen=True, order=True)
class Money:
    """An amount in paisa. Immutable, so it is safe to share between threads."""

    paisa: int

    def __post_init__(self) -> None:
        if isinstance(self.paisa, bool) or not isinstance(self.paisa, int):
            raise InvalidAmountError("amount", "must be a whole number of paisa")

    @classmethod
    def zero(cls) -> Money:
        return cls(0)

    @classmethod
    def from_rupees(cls, value: str | int | Decimal) -> Money:
        """Parse a rupee amount such as "1250.50". At most 2 decimal places."""
        try:
            amount = Decimal(str(value))
        except InvalidOperation as exc:
            raise InvalidAmountError("amount", "is not a number") from exc
        if not amount.is_finite():
            raise InvalidAmountError("amount", "is not a number")
        if amount.as_tuple().exponent < -2:  # type: ignore[operator]
            raise InvalidAmountError("amount", "has more than 2 decimal places")
        return cls(int(amount * PAISA_PER_RUPEE))

    def __add__(self, other: Money) -> Money:
        return Money(self.paisa + other.paisa)

    def __sub__(self, other: Money) -> Money:
        return Money(self.paisa - other.paisa)

    def __neg__(self) -> Money:
        return Money(-self.paisa)

    def is_zero(self) -> bool:
        return self.paisa == 0

    def to_rupees_str(self) -> str:
        sign = "-" if self.paisa < 0 else ""
        rupees, paisa = divmod(abs(self.paisa), PAISA_PER_RUPEE)
        return f"{sign}{rupees}.{paisa:02d}"

    def allocate(self, weights: list[int]) -> list[Money]:
        """Split this amount in proportion to ``weights``.

        Uses the largest-remainder method, so the parts always add up to exactly
        this amount. Leftover paisa go to the parts with the largest remainder;
        ties go to the earlier position. Callers put the payer first so the
        payer absorbs rounding (FR-05).
        """
        if self.paisa < 0:
            raise InvalidAmountError("amount", "cannot allocate a negative amount")
        if not weights:
            raise InvalidAmountError("weights", "at least one weight is required")
        if any(w < 0 for w in weights):
            raise InvalidAmountError("weights", "weights cannot be negative")
        total_weight = sum(weights)
        if total_weight == 0:
            raise InvalidAmountError("weights", "weights cannot all be zero")

        base = [self.paisa * w // total_weight for w in weights]
        remainders = [self.paisa * w % total_weight for w in weights]
        leftover = self.paisa - sum(base)
        # Highest remainder first; stable sort keeps earlier positions first on ties.
        order = sorted(range(len(weights)), key=lambda i: -remainders[i])
        for i in order[:leftover]:
            base[i] += 1
        return [Money(p) for p in base]
