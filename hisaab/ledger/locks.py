"""Per-group locks (thread-safety strategy, SE423 M1 Table 6.1).

* One threading.Lock per group id, so writes inside one group are serialised
  while different groups still run in parallel.
* The lock map itself is guarded by a separate lock.
* Locks are taken with a timeout, so a stuck thread cannot hang later requests.
* A thread may hold at most one group lock at a time, which removes circular
  wait, so deadlock cannot happen by construction.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from hisaab.domain.errors import LockTimeoutError, NestedGroupLockError

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TIMEOUT_S = 5.0


class LockRegistry:
    def __init__(self, timeout_s: float = DEFAULT_LOCK_TIMEOUT_S) -> None:
        self._timeout_s = timeout_s
        self._locks: dict[int, threading.Lock] = {}
        self._guard = threading.Lock()
        self._held = threading.local()

    def _lock_for(self, group_id: int) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(group_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[group_id] = lock
            return lock

    def held_group(self) -> int | None:
        return getattr(self._held, "group_id", None)

    @contextmanager
    def hold(self, group_id: int) -> Iterator[None]:
        current = self.held_group()
        if current == group_id:  # re-entry by the same thread for the same group
            yield
            return
        if current is not None:
            raise NestedGroupLockError(
                f"thread already holds group {current}; refusing to lock group {group_id}"
            )
        lock = self._lock_for(group_id)
        if not lock.acquire(timeout=self._timeout_s):
            logger.warning("lock timeout on group %s after %.1fs", group_id, self._timeout_s)
            raise LockTimeoutError(f"group {group_id} is busy, try again")
        self._held.group_id = group_id
        try:
            yield
        finally:
            self._held.group_id = None
            lock.release()
