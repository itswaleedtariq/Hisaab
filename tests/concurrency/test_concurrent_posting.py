"""QR-04 / FR-13: concurrent posting to one group loses no updates.

N threads start together on a threading.Barrier and each posts M expenses to
the same group. Afterwards the group must have exactly N x M expenses and its
balances must sum to zero paisa.
"""

import threading

import pytest

from hisaab.domain.money import Money
from hisaab.expenses.service import NewExpense

THREADS = 20
PER_THREAD = 50


def hammer(trip, threads=THREADS, per_thread=PER_THREAD):
    people = [trip.ali, trip.sara, trip.bilal]
    barrier = threading.Barrier(threads)
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        payer = people[n % 3]
        try:
            barrier.wait()
            for i in range(per_thread):
                trip.c.expenses.record(
                    NewExpense(trip.group_id, payer, Money(1000 + n * 7 + i), "equal", people),
                    payer,
                )
        except BaseException as exc:  # noqa: BLE001 - collected and re-asserted below
            errors.append(exc)

    workers = [threading.Thread(target=worker, args=(n,)) for n in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return errors


def assert_consistent(trip, expected):
    expenses = trip.c.expenses.list_for_group(trip.group_id, trip.ali)
    assert len(expenses) == expected
    balances = trip.c.ledger_repo.balances(trip.group_id)
    assert sum(b.paisa for b in balances.values()) == 0
    # every expense produced exactly its own ledger rows
    ledger_ids = {e.source_id for e in trip.c.ledger_repo.entries(trip.group_id)}
    assert ledger_ids == {e.id for e in expenses}


def test_qr04_in_memory(trip):
    assert hammer(trip) == []
    assert_consistent(trip, THREADS * PER_THREAD)


@pytest.mark.parametrize("run", range(3))
def test_qr04_sqlite(sqlite_trip, run):
    assert hammer(sqlite_trip) == []
    assert_consistent(sqlite_trip, THREADS * PER_THREAD)


def test_report_snapshot_while_posting(sqlite_trip):
    """A report generated during concurrent posting still completes."""
    c = sqlite_trip.c
    job = c.reports.request(sqlite_trip.group_id, sqlite_trip.ali, "2026-11", "csv")
    assert hammer(sqlite_trip, threads=5, per_thread=20) == []
    c.reports.last_future.result(timeout=10)
    assert c.reports.status(job.id, sqlite_trip.ali).status.value == "done"


def test_concurrent_settle_up_and_posting_keep_zero_sum(sqlite_trip):
    c, trip = sqlite_trip.c, sqlite_trip
    for _ in range(5):
        trip.spend(trip.ali, "100")
    barrier = threading.Barrier(2)
    errors = []

    def settle():
        barrier.wait()
        try:
            c.settlement.settle_up(trip.group_id, trip.ali)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t = threading.Thread(target=settle)
    t.start()
    barrier.wait()
    for _ in range(20):
        trip.spend(trip.sara, "10")
    t.join()
    assert errors == []
    assert sum(b.paisa for b in c.ledger_repo.balances(trip.group_id).values()) == 0
