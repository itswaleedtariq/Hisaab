"""Routes for Users (FR-01)."""

from __future__ import annotations

from fastapi import APIRouter

from hisaab.api.routes.deps import ContainerDep
from hisaab.api.schemas import RegisterUserIn, UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=201, response_model=UserOut)
def register(body: RegisterUserIn, c: ContainerDep) -> UserOut:
    user = c.users.register(body.name, body.email)
    return UserOut(id=user.id, name=user.name, email=user.email)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, c: ContainerDep) -> UserOut:
    user = c.users.get(user_id)
    return UserOut(id=user.id, name=user.name, email=user.email)
