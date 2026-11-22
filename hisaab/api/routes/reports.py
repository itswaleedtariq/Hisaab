"""Routes for background reports (FR-14, FR-15)."""

from __future__ import annotations

from fastapi import APIRouter

from hisaab.api.routes.deps import ActorDep, ContainerDep
from hisaab.api.schemas import ReportIn, ReportJobOut
from hisaab.domain.models import ReportJob

router = APIRouter(tags=["reports"])


def _out(job: ReportJob) -> ReportJobOut:
    return ReportJobOut(
        id=job.id,  # type: ignore[arg-type]
        group_id=job.group_id,
        period=job.period,
        format=job.format,
        status=job.status.value,
        error=job.error,
    )


@router.post("/groups/{group_id}/reports", status_code=202, response_model=ReportJobOut)
def request_report(group_id: int, body: ReportIn, actor: ActorDep, c: ContainerDep) -> ReportJobOut:
    return _out(c.reports.request(group_id, actor, body.period, body.format))


@router.get("/reports/{job_id}", response_model=ReportJobOut)
def report_status(job_id: int, actor: ActorDep, c: ContainerDep) -> ReportJobOut:
    return _out(c.reports.status(job_id, actor))
