"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from hisaab.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_actor(x_user_id: Annotated[int, Header(ge=1)]) -> int:
    """The caller's user id from the X-User-Id header (M2 identity, see risk R10)."""
    return x_user_id


ContainerDep = Annotated[Container, Depends(get_container)]
ActorDep = Annotated[int, Depends(get_actor)]
