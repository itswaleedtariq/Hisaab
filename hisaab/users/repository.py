"""Repository interfaces for Users and Groups (ISP: one per aggregate)."""

from __future__ import annotations

import itertools
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from hisaab.domain.errors import DuplicateEmailError
from hisaab.domain.models import Group, User


class UserRepository(ABC):
    @abstractmethod
    def add(self, name: str, email: str, created_at: datetime) -> User:
        """Store a new user. Raises DuplicateEmailError if the email is taken."""

    @abstractmethod
    def get(self, user_id: int) -> User | None: ...

    @abstractmethod
    def find_by_email(self, email: str) -> User | None: ...


class GroupRepository(ABC):
    @abstractmethod
    def add(self, name: str, admin_id: int, created_at: datetime) -> Group: ...

    @abstractmethod
    def get(self, group_id: int) -> Group | None: ...

    @abstractmethod
    def add_member(self, group_id: int, user_id: int, joined_at: datetime) -> None: ...

    @abstractmethod
    def remove_member(self, group_id: int, user_id: int) -> None: ...

    @abstractmethod
    def member_ids(self, group_id: int) -> list[int]:
        """Member ids in the order they joined."""

    def is_member(self, group_id: int, user_id: int) -> bool:
        return user_id in self.member_ids(group_id)


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[int, User] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, name: str, email: str, created_at: datetime) -> User:
        with self._lock:
            if any(u.email == email for u in self._users.values()):
                raise DuplicateEmailError(f"email {email} is already registered")
            user = User(next(self._ids), name, email, created_at)
            self._users[user.id] = user
            return user

    def get(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def find_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)


class InMemoryGroupRepository(GroupRepository):
    def __init__(self) -> None:
        self._groups: dict[int, Group] = {}
        self._members: dict[int, list[int]] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, name: str, admin_id: int, created_at: datetime) -> Group:
        with self._lock:
            group = Group(next(self._ids), name, admin_id, created_at)
            self._groups[group.id] = group
            self._members[group.id] = []
            return group

    def get(self, group_id: int) -> Group | None:
        return self._groups.get(group_id)

    def add_member(self, group_id: int, user_id: int, joined_at: datetime) -> None:
        with self._lock:
            members = self._members.setdefault(group_id, [])
            if user_id not in members:
                members.append(user_id)

    def remove_member(self, group_id: int, user_id: int) -> None:
        with self._lock:
            members = self._members.get(group_id, [])
            if user_id in members:
                members.remove(user_id)

    def member_ids(self, group_id: int) -> list[int]:
        with self._lock:
            return list(self._members.get(group_id, []))
