"""SQLite schema constraints and transaction behaviour."""

import sqlite3

import pytest

from hisaab.domain.errors import PersistenceError
from hisaab.persistence.sqlite import Database

NOW = "2026-11-15T10:00:00+00:00"


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "schema.db")
    conn = database.connection()
    conn.execute("INSERT INTO users (name, email, created_at) VALUES ('A', 'a@x.com', ?)", (NOW,))
    conn.execute("INSERT INTO groups (name, admin_id, created_at) VALUES ('G', 1, ?)", (NOW,))
    yield database
    database.close()


def insert_expense(conn, amount=100, split="equal", status="active"):
    conn.execute(
        "INSERT INTO expenses (group_id, payer_id, amount_paisa, split_type, spent_on, status,"
        " created_by, created_at) VALUES (1, 1, ?, ?, '2026-11-01', ?, 1, ?)",
        (amount, split, status, NOW),
    )


@pytest.mark.parametrize(
    "kwargs",
    [{"amount": 0}, {"amount": 1_000_000_001}, {"split": "weird"}, {"status": "deleted"}],
    ids=["amount zero", "amount over max", "bad split type", "bad status"],
)
def test_expense_check_constraints(db, kwargs):
    with pytest.raises(sqlite3.IntegrityError):
        insert_expense(db.connection(), **kwargs)


def test_unique_email_and_self_settlement_constraints(db):
    conn = db.connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO users (name, email, created_at) VALUES ('B', 'a@x.com', ?)",
                     (NOW,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO settlements (group_id, from_user_id, to_user_id, amount_paisa,"
                     " created_at) VALUES (1, 1, 1, 5, ?)", (NOW,))


def test_foreign_keys_are_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.connection().execute(
            "INSERT INTO memberships (group_id, user_id, joined_at) VALUES (1, 99, ?)", (NOW,)
        )


def test_wal_mode_and_schema_version(db):
    conn = db.connection()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1


def test_migrate_is_idempotent(tmp_path):
    Database(tmp_path / "twice.db").close()
    again = Database(tmp_path / "twice.db")
    assert again.query("SELECT COUNT(*) AS n FROM schema_version")[0]["n"] == 1
    again.close()


def test_transaction_rolls_back_on_error(db):
    with pytest.raises(RuntimeError), db.transaction() as conn:
        insert_expense(conn)
        raise RuntimeError("boom")
    assert db.query("SELECT COUNT(*) AS n FROM expenses")[0]["n"] == 0


def test_sqlite_errors_become_persistence_errors(db):
    with pytest.raises(PersistenceError):
        db.query("SELECT * FROM no_such_table")
    with pytest.raises(PersistenceError) as info, db.transaction() as conn:
        insert_expense(conn, amount=0)
    assert isinstance(info.value.__cause__, sqlite3.IntegrityError)
