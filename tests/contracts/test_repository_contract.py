"""LSP contract: the in-memory and SQLite repositories must be interchangeable.

The same tests run against both implementations. If one behaved differently,
the fast unit tests (in-memory) would no longer tell the truth about SQLite.
"""

from datetime import UTC, date, datetime

import pytest

from hisaab.domain.errors import DuplicateEmailError
from hisaab.domain.models import (
    Expense,
    ExpenseStatus,
    JobStatus,
    LedgerEntry,
    LedgerSource,
    ReportJob,
    Settlement,
    Share,
    SplitType,
)
from hisaab.domain.money import Money
from hisaab.expenses.repository import InMemoryExpenseRepository
from hisaab.ledger.repository import InMemoryLedgerRepository, InMemorySettlementRepository
from hisaab.persistence.sqlite import (
    Database,
    SqliteExpenseRepository,
    SqliteGroupRepository,
    SqliteLedgerRepository,
    SqliteReportJobRepository,
    SqliteSettlementRepository,
    SqliteUserRepository,
)
from hisaab.reports.repository import InMemoryReportJobRepository
from hisaab.users.repository import InMemoryGroupRepository, InMemoryUserRepository

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", "sqlite"])
def repos(request, tmp_path):
    if request.param == "memory":
        r = dict(
            users=InMemoryUserRepository(), groups=InMemoryGroupRepository(),
            expenses=InMemoryExpenseRepository(), ledger=InMemoryLedgerRepository(),
            settlements=InMemorySettlementRepository(), jobs=InMemoryReportJobRepository(),
        )
        yield r
        return
    db = Database(tmp_path / "contract.db")
    yield dict(
        users=SqliteUserRepository(db), groups=SqliteGroupRepository(db),
        expenses=SqliteExpenseRepository(db), ledger=SqliteLedgerRepository(db),
        settlements=SqliteSettlementRepository(db), jobs=SqliteReportJobRepository(db),
    )
    db.close()


@pytest.fixture
def seeded(repos):
    a = repos["users"].add("Ali", "ali@example.com", NOW)
    b = repos["users"].add("Sara", "sara@example.com", NOW)
    g = repos["groups"].add("Trip", a.id, NOW)
    repos["groups"].add_member(g.id, a.id, NOW)
    repos["groups"].add_member(g.id, b.id, NOW)
    return repos, a.id, b.id, g.id


def expense(group_id, payer, other, key=None, spent=date(2026, 11, 3)):
    return Expense(
        id=None, group_id=group_id, payer_id=payer, amount=Money(1000),
        split_type=SplitType.EQUAL,
        shares=(Share(payer, Money(500)), Share(other, Money(500))),
        spent_on=spent, created_by=payer, created_at=NOW, idempotency_key=key,
    )


def test_users(repos):
    u = repos["users"].add("Ali", "ali@example.com", NOW)
    assert repos["users"].get(u.id) == u
    assert repos["users"].find_by_email("ali@example.com") == u
    assert repos["users"].get(999) is None
    with pytest.raises(DuplicateEmailError):
        repos["users"].add("Other", "ali@example.com", NOW)


def test_groups_and_membership_order(seeded):
    repos, a, b, g = seeded
    assert repos["groups"].get(g).admin_id == a
    assert repos["groups"].member_ids(g) == [a, b]
    repos["groups"].add_member(g, b, NOW)  # adding twice is harmless
    assert repos["groups"].member_ids(g) == [a, b]
    repos["groups"].remove_member(g, b)
    assert repos["groups"].member_ids(g) == [a]
    assert repos["groups"].get(999) is None


def test_expenses_round_trip(seeded):
    repos, a, b, g = seeded
    saved = repos["expenses"].add(expense(g, a, b, key="k1"))
    assert saved.id is not None
    assert repos["expenses"].get(saved.id) == saved
    assert repos["expenses"].find_by_idempotency_key("k1") == saved
    assert repos["expenses"].find_by_idempotency_key("nope") is None
    repos["expenses"].set_status(saved.id, ExpenseStatus.VOIDED)
    assert repos["expenses"].get(saved.id).status is ExpenseStatus.VOIDED


def test_expenses_filter_by_month(seeded):
    repos, a, b, g = seeded
    repos["expenses"].add(expense(g, a, b, spent=date(2026, 10, 31)))
    nov = repos["expenses"].add(expense(g, a, b, spent=date(2026, 11, 1)))
    assert [e.id for e in repos["expenses"].list_for_group(g, "2026-11")] == [nov.id]
    assert len(repos["expenses"].list_for_group(g)) == 2


def test_ledger_balances(seeded):
    repos, a, b, g = seeded
    repos["ledger"].append([
        LedgerEntry(g, a, Money(500), LedgerSource.EXPENSE, 1, NOW),
        LedgerEntry(g, b, Money(-500), LedgerSource.EXPENSE, 1, NOW),
        LedgerEntry(g, b, Money(200), LedgerSource.SETTLEMENT, 1, NOW),
    ])
    assert repos["ledger"].balances(g) == {a: Money(500), b: Money(-300)}
    assert repos["ledger"].balance_of(g, b) == Money(-300)
    assert repos["ledger"].balance_of(g, 999) == Money(0)
    assert len(repos["ledger"].entries(g)) == 3


def test_settlements(seeded):
    repos, a, b, g = seeded
    s = repos["settlements"].add(Settlement(None, g, b, a, Money(100), NOW))
    assert s.id is not None
    assert repos["settlements"].list_for_group(g) == [s]


def test_report_jobs(seeded):
    repos, a, _b, g = seeded
    job = repos["jobs"].add(ReportJob(None, g, "2026-11", "csv", JobStatus.PENDING, a, NOW))
    assert repos["jobs"].get(job.id) == job
    done = ReportJob(job.id, g, "2026-11", "csv", JobStatus.DONE, a, NOW,
                     file_path="x.csv", finished_at=NOW)
    repos["jobs"].update(done)
    assert repos["jobs"].get(job.id) == done
    assert repos["jobs"].get(999) is None



def test_in_memory_user_lookup_is_safe_during_concurrent_adds():
    """DEF-05: reads must hold the repository lock, as SQLite isolates its own reads."""
    import sys
    import threading

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads very often so the race shows up every run
    errors = []
    try:
        for _trial in range(5):
            repo, stop = InMemoryUserRepository(), threading.Event()

            def writer(repo=repo, stop=stop):
                i = 0
                while not stop.is_set():
                    repo.add("u", f"u{i}@example.com", NOW)
                    i += 1

            def reader(repo=repo):
                try:
                    for _ in range(2000):
                        repo.find_by_email("nobody@example.com")
                except RuntimeError as exc:
                    errors.append(exc)

            w, r = threading.Thread(target=writer), threading.Thread(target=reader)
            w.start()
            r.start()
            r.join()
            stop.set()
            w.join()
    finally:
        sys.setswitchinterval(old)
    assert errors == []
