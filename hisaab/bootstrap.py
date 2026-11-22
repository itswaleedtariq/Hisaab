"""Composition root. The only place that knows which concrete classes are used.

Every service receives its dependencies through its constructor (DIP). Tests
call build_in_memory(); the API calls build_sqlite().
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hisaab.domain.clock import Clock, SystemClock
from hisaab.domain.uow import UnitOfWork
from hisaab.events.bus import EventBus
from hisaab.expenses.repository import ExpenseRepository, InMemoryExpenseRepository
from hisaab.expenses.service import ExpenseService
from hisaab.ledger.facade import SettlementFacade
from hisaab.ledger.locks import LockRegistry
from hisaab.ledger.planner import SettlementPlanner
from hisaab.ledger.repository import (
    InMemoryLedgerRepository,
    InMemorySettlementRepository,
    LedgerRepository,
    SettlementRepository,
)
from hisaab.ledger.service import LedgerService
from hisaab.persistence.memory import InMemoryUnitOfWork
from hisaab.persistence.sqlite import (
    Database,
    SqliteExpenseRepository,
    SqliteGroupRepository,
    SqliteLedgerRepository,
    SqliteReportJobRepository,
    SqliteSettlementRepository,
    SqliteUnitOfWork,
    SqliteUserRepository,
)
from hisaab.reports.exporters import CsvExporter
from hisaab.reports.repository import InMemoryReportJobRepository, ReportJobRepository
from hisaab.reports.service import ReportService
from hisaab.reports.worker import ReportWorker
from hisaab.splitting.factory import default_factory
from hisaab.users.repository import (
    GroupRepository,
    InMemoryGroupRepository,
    InMemoryUserRepository,
    UserRepository,
)
from hisaab.users.service import GroupService, UserService


@dataclass
class Container:
    users: UserService
    groups: GroupService
    expenses: ExpenseService
    settlement: SettlementFacade
    reports: ReportService
    worker: ReportWorker
    ledger_repo: LedgerRepository
    bus: EventBus
    locks: LockRegistry
    database: Database | None = None

    def close(self) -> None:
        self.worker.shutdown(wait=True)
        if self.database is not None:
            self.database.close()


@dataclass
class _Repos:
    users: UserRepository
    groups: GroupRepository
    expenses: ExpenseRepository
    ledger: LedgerRepository
    settlements: SettlementRepository
    jobs: ReportJobRepository


def _wire(
    repos: _Repos,
    uow: UnitOfWork,
    locks: LockRegistry,
    clock: Clock,
    report_dir: Path,
    database: Database | None = None,
) -> Container:
    bus = EventBus()
    LedgerService(repos.ledger, clock).subscribe_to(bus)

    users = UserService(repos.users, clock)
    groups = GroupService(repos.groups, repos.users, repos.ledger, uow, clock)
    expenses = ExpenseService(repos.expenses, groups, default_factory(), bus, uow, clock)
    settlement = SettlementFacade(
        repos.ledger, SettlementPlanner(), repos.settlements, bus, groups, uow, clock
    )
    worker = ReportWorker(
        repos.jobs, repos.expenses, {"csv": CsvExporter()}, uow, clock, report_dir
    )
    reports = ReportService(repos.jobs, worker, groups, clock)
    return Container(
        users, groups, expenses, settlement, reports, worker, repos.ledger, bus, locks, database
    )


def build_in_memory(clock: Clock | None = None, report_dir: Path | None = None) -> Container:
    locks = LockRegistry()
    repos = _Repos(
        InMemoryUserRepository(),
        InMemoryGroupRepository(),
        InMemoryExpenseRepository(),
        InMemoryLedgerRepository(),
        InMemorySettlementRepository(),
        InMemoryReportJobRepository(),
    )
    return _wire(
        repos, InMemoryUnitOfWork(locks), locks, clock or SystemClock(),
        report_dir or Path("data/reports"),
    )


def build_sqlite(
    db_path: str | Path, clock: Clock | None = None, report_dir: Path | None = None
) -> Container:
    db = Database(db_path)
    locks = LockRegistry()
    repos = _Repos(
        SqliteUserRepository(db),
        SqliteGroupRepository(db),
        SqliteExpenseRepository(db),
        SqliteLedgerRepository(db),
        SqliteSettlementRepository(db),
        SqliteReportJobRepository(db),
    )
    return _wire(
        repos, SqliteUnitOfWork(db, locks), locks, clock or SystemClock(),
        report_dir or Path("data/reports"), database=db,
    )
