"""Pydantic request and response models: the first line of input validation."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from hisaab.domain.models import Expense, Settlement, Transfer
from hisaab.domain.money import Money

RupeeAmount = Annotated[str, StringConstraints(pattern=r"^\d{1,8}(\.\d{1,2})?$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=80)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterUserIn(_Strict):
    name: Name
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class CreateGroupIn(_Strict):
    name: Name


class GroupOut(BaseModel):
    id: int
    name: str
    admin_id: int


class AddMemberIn(_Strict):
    user_id: int = Field(ge=1)


class ExpenseIn(_Strict):
    payer_id: int = Field(ge=1)
    amount: RupeeAmount
    split_type: str
    participants: list[int] = Field(min_length=1, max_length=50)
    amounts: dict[int, RupeeAmount] | None = None
    percentages: dict[int, str] | None = None
    shares: dict[int, int] | None = None
    spent_on: date | None = None
    category: Annotated[str, StringConstraints(max_length=40)] | None = None
    description: Annotated[str, StringConstraints(max_length=200)] | None = None

    def split_params(self) -> dict:
        return {
            k: v
            for k, v in (
                ("amounts", self.amounts),
                ("percentages", self.percentages),
                ("shares", self.shares),
            )
            if v is not None
        }


class ShareOut(BaseModel):
    user_id: int
    amount: str


class ExpenseOut(BaseModel):
    id: int
    group_id: int
    payer_id: int
    amount: str
    split_type: str
    status: str
    spent_on: date
    category: str | None
    description: str | None
    shares: list[ShareOut]

    @classmethod
    def of(cls, e: Expense) -> ExpenseOut:
        return cls(
            id=e.id,  # type: ignore[arg-type]
            group_id=e.group_id,
            payer_id=e.payer_id,
            amount=e.amount.to_rupees_str(),
            split_type=e.split_type.value,
            status=e.status.value,
            spent_on=e.spent_on,
            category=e.category,
            description=e.description,
            shares=[ShareOut(user_id=s.user_id, amount=s.amount.to_rupees_str()) for s in e.shares],
        )


class BalanceOut(BaseModel):
    user_id: int
    balance: str


class TransferOut(BaseModel):
    from_user_id: int
    to_user_id: int
    amount: str

    @classmethod
    def of(cls, t: Transfer | Settlement) -> TransferOut:
        return cls(
            from_user_id=t.from_user_id, to_user_id=t.to_user_id, amount=t.amount.to_rupees_str()
        )


class PaymentIn(_Strict):
    from_user_id: int = Field(ge=1)
    to_user_id: int = Field(ge=1)
    amount: RupeeAmount


class ReportIn(_Strict):
    period: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}$")]
    format: str = "csv"


class ReportJobOut(BaseModel):
    id: int
    group_id: int
    period: str
    format: str
    status: str
    error: str | None = None


def money(text: str) -> Money:
    return Money.from_rupees(text)
