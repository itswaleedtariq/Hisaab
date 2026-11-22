"""Background report generation on a thread pool (FR-14). Owner: Waleed Tariq.

Job status moves pending -> running -> done | failed. A failed job keeps its
error message. The worker reads all expenses inside one read snapshot, so the
report reflects a single point in time even while new expenses arrive.
"""

from __future__ import annotations

import dataclasses
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from hisaab.domain.clock import Clock
from hisaab.domain.errors import HisaabError
from hisaab.domain.models import JobStatus, ReportJob
from hisaab.domain.uow import UnitOfWork
from hisaab.expenses.repository import ExpenseRepository
from hisaab.reports.exporters import ReportExporter
from hisaab.reports.repository import ReportJobRepository

logger = logging.getLogger(__name__)


class ReportWorker:
    def __init__(
        self,
        jobs: ReportJobRepository,
        expenses: ExpenseRepository,
        exporters: dict[str, ReportExporter],
        uow: UnitOfWork,
        clock: Clock,
        output_dir: Path,
        max_workers: int = 2,
    ) -> None:
        self._jobs = jobs
        self._expenses = expenses
        self._exporters = exporters
        self._uow = uow
        self._clock = clock
        self._output_dir = output_dir
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="report")

    def submit(self, job: ReportJob) -> Future[None]:
        return self._pool.submit(self._run, job)

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def _run(self, job: ReportJob) -> None:
        running = dataclasses.replace(job, status=JobStatus.RUNNING)
        self._jobs.update(running)
        try:
            exporter = self._exporters[job.format]
            with self._uow.read_snapshot():
                expenses = self._expenses.list_for_group(job.group_id, job.period)
            content = exporter.render(expenses)
            self._output_dir.mkdir(parents=True, exist_ok=True)
            name = f"group{job.group_id}_{job.period}_job{job.id}.{exporter.extension}"
            path = self._output_dir / name
            path.write_text(content, encoding="utf-8")
            done = dataclasses.replace(
                running, status=JobStatus.DONE, file_path=str(path), finished_at=self._clock.now()
            )
            self._jobs.update(done)
            logger.info("report job %s done: %s", job.id, path)
        except (HisaabError, OSError, KeyError) as exc:
            failed = dataclasses.replace(
                running, status=JobStatus.FAILED, error=str(exc), finished_at=self._clock.now()
            )
            self._jobs.update(failed)
            logger.error("report job %s failed: %s", job.id, exc)
