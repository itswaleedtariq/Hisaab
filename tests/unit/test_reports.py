"""Reports (FR-14, FR-15). Owner: Waleed Tariq."""

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from hisaab.domain.errors import NotGroupMemberError, ReportJobNotFoundError, ValidationError
from hisaab.domain.models import Expense, JobStatus, Share, SplitType
from hisaab.domain.money import Money
from hisaab.expenses.repository import InMemoryExpenseRepository
from hisaab.reports.exporters import CsvExporter
from hisaab.reports.repository import InMemoryReportJobRepository
from hisaab.reports.service import ReportService
from hisaab.reports.worker import ReportWorker
from tests.conftest import NOW


@pytest.fixture
def r(people, tmp_path):
    people.expense_repo = InMemoryExpenseRepository()
    jobs = InMemoryReportJobRepository()
    people.worker = ReportWorker(jobs, people.expense_repo, {"csv": CsvExporter()}, people.uow,
                                 people.clock, tmp_path / "reports")
    people.reports = ReportService(jobs, people.worker, people.groups, people.clock)
    yield people
    people.worker.shutdown()


def add_expense(r, spent_on=date(2026, 11, 3), description=None):
    return r.expense_repo.add(Expense(
        id=None, group_id=r.group_id, payer_id=r.ali, amount=Money(30000),
        split_type=SplitType.EQUAL,
        shares=tuple(Share(u, Money(10000)) for u in (r.ali, r.sara, r.bilal)),
        spent_on=spent_on, created_by=r.ali, created_at=NOW, description=description,
    ))


def run(r, actor, period="2026-11", fmt="csv"):
    job = r.reports.request(r.group_id, actor, period, fmt)
    r.reports.last_future.result(timeout=5)
    return job, r.reports.status(job.id, actor)


def test_report_job_runs_in_background_and_writes_csv(r):
    add_expense(r)
    add_expense(r, spent_on=date(2026, 10, 30))  # other month, must not appear
    job, done = run(r, r.sara)
    assert job.status is JobStatus.PENDING
    assert done.status is JobStatus.DONE
    lines = Path(done.file_path).read_text().splitlines()
    assert lines[0].startswith("expense_id,spent_on")
    assert len(lines) == 2
    assert lines[1].endswith(f"{r.ali}:100.00;{r.sara}:100.00;{r.bilal}:100.00")


def test_empty_month_gives_header_only(r):
    """TC-BB-48: a month with no expenses."""
    _job, done = run(r, r.ali, period="2026-01")
    assert len(Path(done.file_path).read_text().splitlines()) == 1


@pytest.mark.parametrize(
    ("period", "fmt"),
    [
        pytest.param("2026-13", "csv", id="TC-BB-46 month 13"),
        pytest.param("2026-1", "csv", id="TC-BB-47 one-digit month"),
        pytest.param("2026-11", "pdf", id="TC-BB-49 unsupported format"),
    ],
)
def test_invalid_report_requests(r, period, fmt):
    with pytest.raises(ValidationError):
        r.reports.request(r.group_id, r.ali, period, fmt)


def test_report_access_rules(r):
    zara = r.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        r.reports.request(r.group_id, zara, "2026-11", "csv")
    job, _done = run(r, r.ali)
    with pytest.raises(NotGroupMemberError):
        r.reports.status(job.id, zara)
    with pytest.raises(ReportJobNotFoundError):
        r.reports.status(999, r.ali)


def test_failed_job_keeps_its_error(r, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    r.worker._output_dir = blocker  # writing into a file path must fail
    _job, failed = run(r, r.ali)
    assert failed.status is JobStatus.FAILED
    assert failed.error


def test_csv_cells_cannot_start_a_formula(r):
    expense = dataclasses.replace(add_expense(r), description="=HYPERLINK(1)")
    row = CsvExporter().render([expense]).splitlines()[1]
    assert ",'=HYPERLINK(1)," in row
