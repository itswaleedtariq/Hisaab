"""Repository for report jobs."""

from __future__ import annotations

import dataclasses
import itertools
import threading
from abc import ABC, abstractmethod

from hisaab.domain.models import ReportJob


class ReportJobRepository(ABC):
    @abstractmethod
    def add(self, job: ReportJob) -> ReportJob: ...

    @abstractmethod
    def get(self, job_id: int) -> ReportJob | None: ...

    @abstractmethod
    def update(self, job: ReportJob) -> None: ...


class InMemoryReportJobRepository(ReportJobRepository):
    def __init__(self) -> None:
        self._rows: dict[int, ReportJob] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, job: ReportJob) -> ReportJob:
        with self._lock:
            stored = dataclasses.replace(job, id=next(self._ids))
            self._rows[stored.id] = stored  # type: ignore[index]
            return stored

    def get(self, job_id: int) -> ReportJob | None:
        with self._lock:
            return self._rows.get(job_id)

    def update(self, job: ReportJob) -> None:
        with self._lock:
            self._rows[job.id] = job  # type: ignore[index]
