"""Routes for Groups and membership (FR-02, FR-03)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from hisaab.api.routes.deps import ActorDep, ContainerDep
from hisaab.api.schemas import AddMemberIn, CreateGroupIn, GroupOut

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", status_code=201, response_model=GroupOut)
def create_group(body: CreateGroupIn, actor: ActorDep, c: ContainerDep) -> GroupOut:
    group = c.groups.create_group(body.name, actor)
    return GroupOut(id=group.id, name=group.name, admin_id=group.admin_id)


@router.get("/{group_id}/members", response_model=list[int])
def list_members(group_id: int, actor: ActorDep, c: ContainerDep) -> list[int]:
    return c.groups.members(group_id, actor)


@router.post("/{group_id}/members", status_code=204)
def add_member(group_id: int, body: AddMemberIn, actor: ActorDep, c: ContainerDep) -> Response:
    c.groups.add_member(group_id, actor, body.user_id)
    return Response(status_code=204)


@router.delete("/{group_id}/members/{user_id}", status_code=204)
def remove_member(group_id: int, user_id: int, actor: ActorDep, c: ContainerDep) -> Response:
    c.groups.remove_member(group_id, actor, user_id)
    return Response(status_code=204)
