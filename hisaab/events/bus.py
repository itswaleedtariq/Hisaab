"""Observer pattern: an in-process, synchronous event bus.

Handlers run synchronously in the publisher's thread, inside the publisher's
unit of work. So if the ledger handler fails, the whole expense is rolled back
and the ledger can never miss an expense (see SE423 M1, Table 5.1).
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], None]


class EventPublisher(ABC):
    """What a publisher (e.g. ExpenseService) depends on. Nothing else."""

    @abstractmethod
    def publish(self, event: object) -> None: ...


class EventBus(EventPublisher):
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)
        self._guard = threading.Lock()

    def subscribe(self, event_type: type, handler: Handler) -> None:
        with self._guard:
            self._handlers[event_type].append(handler)

    def publish(self, event: object) -> None:
        with self._guard:
            handlers = list(self._handlers.get(type(event), ()))
        for handler in handlers:
            logger.debug("dispatch %s to %s", type(event).__name__, handler)
            handler(event)  # exceptions propagate so the unit of work rolls back
