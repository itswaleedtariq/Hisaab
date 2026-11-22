"""Reports module: request a report and poll its status (FR-14, FR-15)."""

from __future__ import annotations

import re
from concurrent.futures import Future

from hisaab.domain.clock import Clock
from hisaab.domain.errors import ReportJobNotFoundError, ValidationError
from hisaab.domain.models import JobStatus, ReportJob
from hisaab.expenses.service import Membership
from hisaab.reports.repository import ReportJobRepository
from hisaab.reports.worker import ReportWorker

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ReportService:
    def __init__(
        self,
        jobs: ReportJobRepository,
        worker: ReportWorker,
        membership: Membership,
        clock: Clock,
        formats: tuple[str, ...] = ("csv",),
    ) -> None:
        self._jobs = jobs
        self._worker = worker
        self._membership = membership
        self._clock = clock
        self._formats = formats
        self.last_future: Future[None] | None = None

    def request(self, group_id: int, actor_id: int, period: str, fmt: str) -> ReportJob:
        self._membership.require_member(group_id, actor_id)
        if not PERIOD_RE.match(period or ""):
            raise ValidationError("period", "must be YYYY-MM")
        if fmt not in self._formats:
            raise ValidationError("format", f"must be one of {', '.join(self._formats)}")
        job = self._jobs.add(
            ReportJob(
                id=None,
                group_id=group_id,
                period=period,
                format=fmt,
                status=JobStatus.PENDING,
                requested_by=actor_id,
                created_at=self._clock.now(),
            )
        )
        self.last_future = self._worker.submit(job)
        return job

    def status(self, job_id: int, actor_id: int) -> ReportJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise ReportJobNotFoundError(f"report job {job_id} not found")
        self._membership.require_member(job.group_id, actor_id)
        return job
