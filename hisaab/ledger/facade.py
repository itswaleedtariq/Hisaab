"""Facade pattern: one entry point for balances and settling up (FR-10 to FR-12).

Settling up touches four components: read balances (LedgerReader), plan
(SettlementPlanner), store settlements (SettlementRepository) and publish
events (EventPublisher). API routes call this facade instead of orchestrating
that sequence themselves. Owner: Abdullah Rashid.
"""

from __future__ import annotations

import logging

from hisaab.domain.clock import Clock
from hisaab.domain.errors import InvalidSettlementError, NotGroupAdminError, NotGroupMemberError
from hisaab.domain.models import Settlement, Transfer
from hisaab.domain.money import Money
from hisaab.domain.uow import UnitOfWork
from hisaab.events.bus import EventPublisher
from hisaab.events.events import SettlementRecorded
from hisaab.expenses.service import Membership
from hisaab.ledger.planner import SettlementPlanner
from hisaab.ledger.repository import LedgerReader, SettlementRepository

logger = logging.getLogger(__name__)


class SettlementFacade:
    def __init__(
        self,
        ledger: LedgerReader,
        planner: SettlementPlanner,
        settlements: SettlementRepository,
        publisher: EventPublisher,
        membership: Membership,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._ledger = ledger
        self._planner = planner
        self._settlements = settlements
        self._publisher = publisher
        self._membership = membership
        self._uow = uow
        self._clock = clock

    def balances(self, group_id: int, actor_id: int) -> dict[int, Money]:
        """FR-10: every member's balance, including members at zero."""
        members = self._membership.members(group_id, actor_id)
        with self._uow.read_snapshot():
            raw = self._ledger.balances(group_id)
        return {uid: raw.get(uid, Money.zero()) for uid in members}

    def suggest_plan(self, group_id: int, actor_id: int) -> list[Transfer]:
        """FR-11: suggest a minimal set of payments. Nothing is stored."""
        self._membership.require_member(group_id, actor_id)
        with self._uow.read_snapshot():
            balances = self._ledger.balances(group_id)
        return self._planner.plan(balances)

    def record_payment(
        self, group_id: int, actor_id: int, from_user_id: int, to_user_id: int, amount: Money
    ) -> Settlement:
        """FR-12: record that one member paid another, up to what is owed."""
        with self._uow.for_group(group_id):
            group = self._membership.require_member(group_id, actor_id)
            if actor_id not in (from_user_id, group.admin_id):
                raise NotGroupAdminError("only the payer or the admin can record a payment")
            members = set(self._membership.members(group_id, actor_id))
            if from_user_id not in members or to_user_id not in members:
                raise NotGroupMemberError("both people must be members of the group")
            if from_user_id == to_user_id:
                raise InvalidSettlementError("to_user_id", "cannot pay yourself")
            if amount.paisa <= 0:
                raise InvalidSettlementError("amount", "must be greater than 0")
            owed = self._max_payable(group_id, from_user_id, to_user_id)
            if amount.paisa > owed:
                raise InvalidSettlementError(
                    "amount", f"cannot exceed what is owed ({Money(owed).to_rupees_str()} PKR)"
                )
            return self._store(group_id, Transfer(from_user_id, to_user_id, amount))

    def settle_up(self, group_id: int, actor_id: int) -> list[Transfer]:
        """Admin records the whole suggested plan in one unit of work."""
        with self._uow.for_group(group_id):
            group = self._membership.require_member(group_id, actor_id)
            if actor_id != group.admin_id:
                raise NotGroupAdminError("only the admin can settle the whole group")
            plan = self._planner.plan(self._ledger.balances(group_id))
            for transfer in plan:
                self._store(group_id, transfer)
            logger.info("group %s settled with %d transfers", group_id, len(plan))
            return plan

    def _max_payable(self, group_id: int, from_user_id: int, to_user_id: int) -> int:
        balances = self._ledger.balances(group_id)
        debt = -balances.get(from_user_id, Money.zero()).paisa
        credit = balances.get(to_user_id, Money.zero()).paisa
        return max(0, min(debt, credit))

    def _store(self, group_id: int, transfer: Transfer) -> Settlement:
        settlement = self._settlements.add(
            Settlement(
                id=None,
                group_id=group_id,
                from_user_id=transfer.from_user_id,
                to_user_id=transfer.to_user_id,
                amount=transfer.amount,
                created_at=self._clock.now(),
            )
        )
        self._publisher.publish(SettlementRecorded(settlement))
        return settlement
