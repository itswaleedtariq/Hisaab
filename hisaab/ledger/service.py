"""Ledger: turns events into append-only ledger entries (FR-09, FR-10, FR-13).

Owner: Abdullah Rashid.

LedgerService never takes a lock itself. Its handlers run synchronously inside
the publisher's unit of work, which already holds the group lock and the
database transaction (see hisaab/domain/uow.py).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from hisaab.domain.clock import Clock
from hisaab.domain.models import LedgerEntry, LedgerSource
from hisaab.domain.money import Money
from hisaab.events.bus import EventBus
from hisaab.events.events import ExpenseRecorded, ExpenseVoided, SettlementRecorded
from hisaab.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


class LedgerService:
    def __init__(self, ledger: LedgerRepository, clock: Clock) -> None:
        self._ledger = ledger
        self._clock = clock

    def subscribe_to(self, bus: EventBus) -> None:
        bus.subscribe(ExpenseRecorded, self.on_expense_recorded)
        bus.subscribe(ExpenseVoided, self.on_expense_voided)
        bus.subscribe(SettlementRecorded, self.on_settlement_recorded)

    def on_expense_recorded(self, event: ExpenseRecorded) -> None:
        expense = event.expense
        net: dict[int, int] = defaultdict(int)
        net[expense.payer_id] += expense.amount.paisa
        for share in expense.shares:
            net[share.user_id] -= share.amount.paisa
        now = self._clock.now()
        entries = [
            LedgerEntry(
                group_id=expense.group_id,
                user_id=uid,
                amount=Money(paisa),
                source_type=LedgerSource.EXPENSE,
                source_id=expense.id,  # type: ignore[arg-type]
                created_at=now,
            )
            for uid, paisa in sorted(net.items())
            if paisa != 0
        ]
        self._ledger.append(entries)

    def on_expense_voided(self, event: ExpenseVoided) -> None:
        expense = event.expense
        originals = [
            e
            for e in self._ledger.entries(expense.group_id)
            if e.source_type is LedgerSource.EXPENSE and e.source_id == expense.id
        ]
        now = self._clock.now()
        reversals = [
            LedgerEntry(
                group_id=e.group_id,
                user_id=e.user_id,
                amount=-e.amount,
                source_type=LedgerSource.VOID,
                source_id=expense.id,  # type: ignore[arg-type]
                created_at=now,
            )
            for e in originals
        ]
        self._ledger.append(reversals)

    def on_settlement_recorded(self, event: SettlementRecorded) -> None:
        s = event.settlement
        now = self._clock.now()
        self._ledger.append(
            [
                LedgerEntry(s.group_id, s.from_user_id, s.amount, LedgerSource.SETTLEMENT,
                            s.id, now),  # type: ignore[arg-type]
                LedgerEntry(s.group_id, s.to_user_id, -s.amount, LedgerSource.SETTLEMENT,
                            s.id, now),  # type: ignore[arg-type]
            ]
        )
