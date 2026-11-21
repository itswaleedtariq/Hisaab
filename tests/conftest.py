"""Shared fixtures. Unit tests use in-memory repositories and a fixed clock.

Imports of Hisaab modules are done inside the fixtures, so a module's tests can
run as soon as that module exists (each TDD cycle stays independent).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


@pytest.fixture
def clock():
    from hisaab.domain.clock import FixedClock

    return FixedClock(NOW)


@dataclass
class Trip:
    """A group of three: ali (admin), sara and bilal, wired through bootstrap."""

    c: Any
    group_id: int
    ali: int
    sara: int
    bilal: int

    def spend(self, payer: int, rupees: str, participants=None, split="equal", **params):
        from hisaab.domain.money import Money
        from hisaab.expenses.service import NewExpense

        return self.c.expenses.record(
            NewExpense(
                group_id=self.group_id,
                payer_id=payer,
                amount=Money.from_rupees(rupees),
                split_type=split,
                participants=participants or [self.ali, self.sara, self.bilal],
                split_params=params,
            ),
            actor_id=payer,
        )


def make_trip(c) -> Trip:
    ali = c.users.register("Ali", "ali@example.com").id
    sara = c.users.register("Sara", "sara@example.com").id
    bilal = c.users.register("Bilal", "bilal@example.com").id
    group = c.groups.create_group("Murree trip", ali)
    c.groups.add_member(group.id, ali, sara)
    c.groups.add_member(group.id, ali, bilal)
    return Trip(c, group.id, ali, sara, bilal)


@pytest.fixture
def app(clock, tmp_path):
    from hisaab.bootstrap import build_in_memory

    container = build_in_memory(clock=clock, report_dir=tmp_path / "reports")
    yield container
    container.close()


@pytest.fixture
def sqlite_app(clock, tmp_path):
    from hisaab.bootstrap import build_sqlite

    container = build_sqlite(tmp_path / "hisaab.db", clock=clock, report_dir=tmp_path / "reports")
    yield container
    container.close()


@pytest.fixture
def trip(app) -> Trip:
    return make_trip(app)


@pytest.fixture
def sqlite_trip(sqlite_app) -> Trip:
    return make_trip(sqlite_app)


# --- small wiring for module-level unit tests (no bootstrap needed) -----------
@pytest.fixture
def people(clock):
    """Users and Groups services on in-memory repositories, with a group of three."""
    from types import SimpleNamespace

    from hisaab.ledger.locks import LockRegistry
    from hisaab.ledger.repository import InMemoryLedgerRepository
    from hisaab.persistence.memory import InMemoryUnitOfWork
    from hisaab.users.repository import InMemoryGroupRepository, InMemoryUserRepository
    from hisaab.users.service import GroupService, UserService

    user_repo = InMemoryUserRepository()
    ledger = InMemoryLedgerRepository()
    uow = InMemoryUnitOfWork(LockRegistry())
    users = UserService(user_repo, clock)
    groups = GroupService(InMemoryGroupRepository(), user_repo, ledger, uow, clock)
    ali = users.register("Ali", "ali@example.com").id
    sara = users.register("Sara", "sara@example.com").id
    bilal = users.register("Bilal", "bilal@example.com").id
    group_id = groups.create_group("Flat 4B", ali).id
    groups.add_member(group_id, ali, sara)
    groups.add_member(group_id, ali, bilal)
    return SimpleNamespace(
        users=users, groups=groups, ledger=ledger, uow=uow, clock=clock,
        group_id=group_id, ali=ali, sara=sara, bilal=bilal,
    )
