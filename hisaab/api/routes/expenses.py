"""Routes for Expenses (FR-04 to FR-09, FR-16)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header

from hisaab.api.routes.deps import ActorDep, ContainerDep
from hisaab.api.schemas import ExpenseIn, ExpenseOut, money
from hisaab.expenses.service import NewExpense

router = APIRouter(tags=["expenses"])

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


@router.post("/groups/{group_id}/expenses", status_code=201, response_model=ExpenseOut)
def record_expense(
    group_id: int,
    body: ExpenseIn,
    actor: ActorDep,
    c: ContainerDep,
    idempotency_key: IdempotencyKey = None,
) -> ExpenseOut:
    expense = c.expenses.record(
        NewExpense(
            group_id=group_id,
            payer_id=body.payer_id,
            amount=money(body.amount),
            split_type=body.split_type,
            participants=body.participants,
            split_params=body.split_params(),
            spent_on=body.spent_on,
            category=body.category,
            description=body.description,
            idempotency_key=idempotency_key,
        ),
        actor,
    )
    return ExpenseOut.of(expense)


@router.get("/groups/{group_id}/expenses", response_model=list[ExpenseOut])
def list_expenses(group_id: int, actor: ActorDep, c: ContainerDep) -> list[ExpenseOut]:
    return [ExpenseOut.of(e) for e in c.expenses.list_for_group(group_id, actor)]


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, actor: ActorDep, c: ContainerDep) -> ExpenseOut:
    return ExpenseOut.of(c.expenses.get(expense_id, actor))


@router.post("/expenses/{expense_id}/void", response_model=ExpenseOut)
def void_expense(expense_id: int, actor: ActorDep, c: ContainerDep) -> ExpenseOut:
    return ExpenseOut.of(c.expenses.void(expense_id, actor))
