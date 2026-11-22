"""Settlement planner (FR-11): at most n-1 transfers for n non-zero members.

Greedy: repeatedly match the largest debtor with the largest creditor. Each
transfer brings at least one of the two to zero, so for n members with a
non-zero balance there are at most n-1 transfers.
"""

from __future__ import annotations

import heapq

from hisaab.domain.errors import InvalidSettlementError
from hisaab.domain.models import Transfer
from hisaab.domain.money import Money


class SettlementPlanner:
    def plan(self, balances: dict[int, Money]) -> list[Transfer]:
        total = sum(b.paisa for b in balances.values())
        if total != 0:
            raise InvalidSettlementError("balances", f"must sum to zero, got {total} paisa")

        # Max-heaps via negated keys; user id breaks ties so the plan is deterministic.
        creditors = [(-b.paisa, uid) for uid, b in balances.items() if b.paisa > 0]
        debtors = [(b.paisa, uid) for uid, b in balances.items() if b.paisa < 0]
        heapq.heapify(creditors)
        heapq.heapify(debtors)

        transfers: list[Transfer] = []
        while creditors and debtors:
            neg_credit, creditor = heapq.heappop(creditors)
            neg_debt, debtor = heapq.heappop(debtors)
            credit, debt = -neg_credit, -neg_debt
            amount = min(credit, debt)
            transfers.append(Transfer(debtor, creditor, Money(amount)))
            if credit > amount:
                heapq.heappush(creditors, (-(credit - amount), creditor))
            if debt > amount:
                heapq.heappush(debtors, (-(debt - amount), debtor))
        return transfers
