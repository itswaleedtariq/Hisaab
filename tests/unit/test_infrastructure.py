"""Event bus, lock registry and clock."""

import threading
import time

import pytest

from hisaab.domain.errors import LockTimeoutError, NestedGroupLockError
from hisaab.events.bus import EventBus
from hisaab.ledger.locks import LockRegistry


def test_bus_delivers_only_to_subscribers_of_that_type():
    bus, got = EventBus(), []
    bus.subscribe(int, got.append)
    bus.publish(5)
    bus.publish("ignored")
    assert got == [5]


def test_bus_handler_error_propagates_to_publisher():
    bus = EventBus()

    def boom(_):
        raise RuntimeError("handler failed")

    bus.subscribe(int, boom)
    with pytest.raises(RuntimeError):
        bus.publish(1)


def test_lock_is_reentrant_for_same_group_on_same_thread():
    locks = LockRegistry()
    with locks.hold(1), locks.hold(1):
        assert locks.held_group() == 1
    assert locks.held_group() is None


def test_holding_two_group_locks_is_refused():
    locks = LockRegistry()
    with locks.hold(1), pytest.raises(NestedGroupLockError), locks.hold(2):
        pass


def test_lock_timeout_raises():
    locks = LockRegistry(timeout_s=0.05)
    started, release = threading.Event(), threading.Event()

    def holder():
        with locks.hold(7):
            started.set()
            release.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    started.wait(2)
    begin = time.monotonic()
    with pytest.raises(LockTimeoutError), locks.hold(7):
        pass
    assert time.monotonic() - begin < 1
    release.set()
    t.join()


def test_different_groups_do_not_block_each_other():
    locks = LockRegistry(timeout_s=0.5)
    inside = threading.Event()
    done = threading.Event()

    def holder():
        with locks.hold(1):
            inside.set()
            done.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    inside.wait(2)
    with locks.hold(2):  # must not wait for group 1
        pass
    done.set()
    t.join()
