"""SQLite adapters for every repository interface, plus the unit of work.

Thread-safety rules (SE423 M1, Table 6.1):
* one connection per thread (sqlite3 connections are not shared);
* WAL mode and busy_timeout=5000 ms;
* every write runs inside BEGIN IMMEDIATE ... COMMIT; nested calls on the same
  thread join the outer transaction instead of opening a new one;
* every sqlite3.Error is re-raised as PersistenceError with the cause chained.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from importlib import resources
from pathlib import Path

from hisaab.domain.errors import DuplicateEmailError, PersistenceError
from hisaab.domain.models import (
    Expense,
    ExpenseStatus,
    Group,
    JobStatus,
    LedgerEntry,
    LedgerSource,
    ReportJob,
    Settlement,
    Share,
    SplitType,
    User,
)
from hisaab.domain.money import Money
from hisaab.domain.uow import UnitOfWork
from hisaab.expenses.repository import ExpenseRepository
from hisaab.ledger.locks import LockRegistry
from hisaab.ledger.repository import LedgerRepository, SettlementRepository
from hisaab.reports.repository import ReportJobRepository
from hisaab.users.repository import GroupRepository, UserRepository

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class Database:
    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._local = threading.local()
        self.migrate()

    # --- connections and transactions --------------------------------------
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            try:
                conn = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=5000")
            except sqlite3.Error as exc:
                raise PersistenceError("could not open the database") from exc
            self._local.conn = conn
            self._local.depth = 0
        return conn

    @contextmanager
    def transaction(self, mode: str = "IMMEDIATE") -> Iterator[sqlite3.Connection]:
        conn = self.connection()
        if self._local.depth > 0:  # join the outer transaction
            self._local.depth += 1
            try:
                yield conn
            finally:
                self._local.depth -= 1
            return
        try:
            conn.execute(f"BEGIN {mode}")
        except sqlite3.Error as exc:
            raise PersistenceError("could not start a transaction") from exc
        self._local.depth = 1
        try:
            yield conn
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise PersistenceError("database write failed") from exc
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            self._local.depth = 0

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        try:
            return self.connection().execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("database read failed") from exc

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # --- schema ----------------------------------------------------------
    def migrate(self) -> None:
        conn = self.connection()
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if exists:
            return
        script = resources.files("hisaab.persistence").joinpath("schema.sql").read_text("utf-8")
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            raise PersistenceError("schema migration failed") from exc
        logger.info("database schema created at version %s", SCHEMA_VERSION)


class SqliteUnitOfWork(UnitOfWork):
    def __init__(self, db: Database, locks: LockRegistry) -> None:
        self._db = db
        self._locks = locks

    @contextmanager
    def for_group(self, group_id: int) -> Iterator[None]:
        with self._locks.hold(group_id), self._db.transaction("IMMEDIATE"):
            yield

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        with self._db.transaction("DEFERRED"):
            yield


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --- Users and Groups ------------------------------------------------------
class SqliteUserRepository(UserRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, name: str, email: str, created_at: datetime) -> User:
        try:
            with self._db.transaction() as conn:
                cur = conn.execute(
                    "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                    (name, email, created_at.isoformat()),
                )
        except PersistenceError as exc:
            if isinstance(exc.__cause__, sqlite3.IntegrityError):
                raise DuplicateEmailError(f"email {email} is already registered") from exc
            raise
        return User(cur.lastrowid, name, email, created_at)  # type: ignore[arg-type]

    def get(self, user_id: int) -> User | None:
        rows = self._db.query("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._row(rows[0]) if rows else None

    def find_by_email(self, email: str) -> User | None:
        rows = self._db.query("SELECT * FROM users WHERE email = ?", (email,))
        return self._row(rows[0]) if rows else None

    @staticmethod
    def _row(r: sqlite3.Row) -> User:
        return User(r["id"], r["name"], r["email"], _dt(r["created_at"]))  # type: ignore[arg-type]


class SqliteGroupRepository(GroupRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, name: str, admin_id: int, created_at: datetime) -> Group:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO groups (name, admin_id, created_at) VALUES (?, ?, ?)",
                (name, admin_id, created_at.isoformat()),
            )
        return Group(cur.lastrowid, name, admin_id, created_at)  # type: ignore[arg-type]

    def get(self, group_id: int) -> Group | None:
        rows = self._db.query("SELECT * FROM groups WHERE id = ?", (group_id,))
        if not rows:
            return None
        r = rows[0]
        return Group(r["id"], r["name"], r["admin_id"], _dt(r["created_at"]))  # type: ignore[arg-type]

    def add_member(self, group_id: int, user_id: int, joined_at: datetime) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO memberships (group_id, user_id, joined_at) VALUES (?, ?, ?)",
                (group_id, user_id, joined_at.isoformat()),
            )

    def remove_member(self, group_id: int, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM memberships WHERE group_id = ? AND user_id = ?", (group_id, user_id)
            )

    def member_ids(self, group_id: int) -> list[int]:
        rows = self._db.query(
            "SELECT user_id FROM memberships WHERE group_id = ? ORDER BY joined_at, rowid",
            (group_id,),
        )
        return [r["user_id"] for r in rows]


# --- Expenses ----------------------------------------------------------------
class SqliteExpenseRepository(ExpenseRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, expense: Expense) -> Expense:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO expenses (group_id, payer_id, amount_paisa, split_type, category,
                       description, spent_on, status, idempotency_key, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    expense.group_id,
                    expense.payer_id,
                    expense.amount.paisa,
                    expense.split_type.value,
                    expense.category,
                    expense.description,
                    expense.spent_on.isoformat(),
                    expense.status.value,
                    expense.idempotency_key,
                    expense.created_by,
                    expense.created_at.isoformat(),
                ),
            )
            expense_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO expense_shares (expense_id, user_id, amount_paisa) VALUES (?, ?, ?)",
                [(expense_id, s.user_id, s.amount.paisa) for s in expense.shares],
            )
        return Expense(**{**expense.__dict__, "id": expense_id})

    def get(self, expense_id: int) -> Expense | None:
        rows = self._db.query("SELECT * FROM expenses WHERE id = ?", (expense_id,))
        return self._load(rows[0]) if rows else None

    def find_by_idempotency_key(self, key: str) -> Expense | None:
        rows = self._db.query("SELECT * FROM expenses WHERE idempotency_key = ?", (key,))
        return self._load(rows[0]) if rows else None

    def set_status(self, expense_id: int, status: ExpenseStatus) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE expenses SET status = ? WHERE id = ?", (status.value, expense_id))

    def list_for_group(self, group_id: int, period: str | None = None) -> list[Expense]:
        if period:
            rows = self._db.query(
                "SELECT * FROM expenses WHERE group_id = ? AND substr(spent_on, 1, 7) = ? "
                "ORDER BY id",
                (group_id, period),
            )
        else:
            rows = self._db.query(
                "SELECT * FROM expenses WHERE group_id = ? ORDER BY id", (group_id,)
            )
        return [self._load(r) for r in rows]

    def _load(self, r: sqlite3.Row) -> Expense:
        shares = self._db.query(
            "SELECT user_id, amount_paisa FROM expense_shares WHERE expense_id = ? "
            "ORDER BY rowid",
            (r["id"],),
        )
        return Expense(
            id=r["id"],
            group_id=r["group_id"],
            payer_id=r["payer_id"],
            amount=Money(r["amount_paisa"]),
            split_type=SplitType(r["split_type"]),
            shares=tuple(Share(s["user_id"], Money(s["amount_paisa"])) for s in shares),
            spent_on=date.fromisoformat(r["spent_on"]),
            created_by=r["created_by"],
            created_at=_dt(r["created_at"]),  # type: ignore[arg-type]
            category=r["category"],
            description=r["description"],
            idempotency_key=r["idempotency_key"],
            status=ExpenseStatus(r["status"]),
        )


# --- Ledger and Settlement --------------------------------------------------
class SqliteLedgerRepository(LedgerRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def append(self, entries: list[LedgerEntry]) -> None:
        with self._db.transaction() as conn:
            conn.executemany(
                """INSERT INTO ledger_entries
                       (group_id, user_id, amount_paisa, source_type, source_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (e.group_id, e.user_id, e.amount.paisa, e.source_type.value, e.source_id,
                     e.created_at.isoformat())
                    for e in entries
                ],
            )

    def entries(self, group_id: int) -> list[LedgerEntry]:
        rows = self._db.query(
            "SELECT * FROM ledger_entries WHERE group_id = ? ORDER BY id", (group_id,)
        )
        return [
            LedgerEntry(
                group_id=r["group_id"],
                user_id=r["user_id"],
                amount=Money(r["amount_paisa"]),
                source_type=LedgerSource(r["source_type"]),
                source_id=r["source_id"],
                created_at=_dt(r["created_at"]),  # type: ignore[arg-type]
                id=r["id"],
            )
            for r in rows
        ]

    def balances(self, group_id: int) -> dict[int, Money]:
        rows = self._db.query(
            "SELECT user_id, SUM(amount_paisa) AS total FROM ledger_entries "
            "WHERE group_id = ? GROUP BY user_id",
            (group_id,),
        )
        return {r["user_id"]: Money(r["total"]) for r in rows}


class SqliteSettlementRepository(SettlementRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, settlement: Settlement) -> Settlement:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO settlements
                       (group_id, from_user_id, to_user_id, amount_paisa, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (settlement.group_id, settlement.from_user_id, settlement.to_user_id,
                 settlement.amount.paisa, settlement.created_at.isoformat()),
            )
        return Settlement(**{**settlement.__dict__, "id": cur.lastrowid})

    def list_for_group(self, group_id: int) -> list[Settlement]:
        rows = self._db.query(
            "SELECT * FROM settlements WHERE group_id = ? ORDER BY id", (group_id,)
        )
        return [
            Settlement(r["id"], r["group_id"], r["from_user_id"], r["to_user_id"],
                       Money(r["amount_paisa"]), _dt(r["created_at"]))  # type: ignore[arg-type]
            for r in rows
        ]


# --- Reports -----------------------------------------------------------------
class SqliteReportJobRepository(ReportJobRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, job: ReportJob) -> ReportJob:
        with self._db.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO report_jobs (group_id, period, format, status, requested_by,
                       created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (job.group_id, job.period, job.format, job.status.value, job.requested_by,
                 job.created_at.isoformat()),
            )
        return ReportJob(**{**job.__dict__, "id": cur.lastrowid})

    def get(self, job_id: int) -> ReportJob | None:
        rows = self._db.query("SELECT * FROM report_jobs WHERE id = ?", (job_id,))
        if not rows:
            return None
        r = rows[0]
        return ReportJob(
            id=r["id"],
            group_id=r["group_id"],
            period=r["period"],
            format=r["format"],
            status=JobStatus(r["status"]),
            requested_by=r["requested_by"],
            created_at=_dt(r["created_at"]),  # type: ignore[arg-type]
            file_path=r["file_path"],
            error=r["error"],
            finished_at=_dt(r["finished_at"]),
        )

    def update(self, job: ReportJob) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE report_jobs SET status = ?, file_path = ?, error = ?, finished_at = ? "
                "WHERE id = ?",
                (job.status.value, job.file_path, job.error,
                 job.finished_at.isoformat() if job.finished_at else None, job.id),
            )
