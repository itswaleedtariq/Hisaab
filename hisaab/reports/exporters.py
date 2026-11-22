"""Report exporters (FR-15). HTML statements are planned for M3."""

from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod

from hisaab.domain.models import Expense


class ReportExporter(ABC):
    extension: str

    @abstractmethod
    def render(self, expenses: list[Expense]) -> str: ...


class CsvExporter(ReportExporter):
    extension = "csv"
    HEADER = [
        "expense_id",
        "spent_on",
        "payer_id",
        "amount_pkr",
        "split_type",
        "category",
        "description",
        "status",
        "shares",
    ]

    def render(self, expenses: list[Expense]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(self.HEADER)
        for e in expenses:
            shares = ";".join(f"{s.user_id}:{s.amount.to_rupees_str()}" for s in e.shares)
            writer.writerow(
                [
                    e.id,
                    e.spent_on.isoformat(),
                    e.payer_id,
                    e.amount.to_rupees_str(),
                    e.split_type.value,
                    _safe(e.category),
                    _safe(e.description),
                    e.status.value,
                    shares,
                ]
            )
        return buffer.getvalue()


def _safe(text: str | None) -> str:
    """Stop spreadsheet formula injection: a cell must not start with = + - @."""
    if not text:
        return ""
    return "'" + text if text[0] in "=+-@" else text
