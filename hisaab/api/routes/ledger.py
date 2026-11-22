"""Routes for balances and settlement (FR-10 to FR-12)."""

from __future__ import annotations

from fastapi import APIRouter

from hisaab.api.routes.deps import ActorDep, ContainerDep
from hisaab.api.schemas import BalanceOut, PaymentIn, TransferOut, money

router = APIRouter(prefix="/groups/{group_id}", tags=["ledger"])


@router.get("/balances", response_model=list[BalanceOut])
def balances(group_id: int, actor: ActorDep, c: ContainerDep) -> list[BalanceOut]:
    return [
        BalanceOut(user_id=uid, balance=b.to_rupees_str())
        for uid, b in c.settlement.balances(group_id, actor).items()
    ]


@router.get("/settlement-plan", response_model=list[TransferOut])
def settlement_plan(group_id: int, actor: ActorDep, c: ContainerDep) -> list[TransferOut]:
    return [TransferOut.of(t) for t in c.settlement.suggest_plan(group_id, actor)]


@router.post("/settlements", status_code=201, response_model=TransferOut)
def record_payment(group_id: int, body: PaymentIn, actor: ActorDep, c: ContainerDep) -> TransferOut:
    settlement = c.settlement.record_payment(
        group_id, actor, body.from_user_id, body.to_user_id, money(body.amount)
    )
    return TransferOut.of(settlement)


@router.post("/settle-up", response_model=list[TransferOut])
def settle_up(group_id: int, actor: ActorDep, c: ContainerDep) -> list[TransferOut]:
    return [TransferOut.of(t) for t in c.settlement.settle_up(group_id, actor)]
