"""Users and Groups module (FR-01 to FR-03). Owner: Waleed Tariq."""

from __future__ import annotations

import logging
import re

from hisaab.domain.clock import Clock
from hisaab.domain.errors import (
    AlreadyMemberError,
    CannotRemoveAdminError,
    DuplicateEmailError,
    GroupNotFoundError,
    GroupTooSmallError,
    InvalidEmailError,
    MemberHasBalanceError,
    NotGroupAdminError,
    NotGroupMemberError,
    UserNotFoundError,
    ValidationError,
)
from hisaab.domain.models import Group, User
from hisaab.domain.uow import UnitOfWork
from hisaab.ledger.repository import LedgerReader
from hisaab.users.repository import GroupRepository, UserRepository

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 254
MIN_MEMBERS_FOR_EXPENSES = 2


def _clean_name(field: str, value: str) -> str:
    name = (value or "").strip()
    if not 1 <= len(name) <= MAX_NAME_LEN:
        raise ValidationError(field, f"must be 1 to {MAX_NAME_LEN} characters")
    return name


class UserService:
    def __init__(self, users: UserRepository, clock: Clock) -> None:
        self._users = users
        self._clock = clock

    def register(self, name: str, email: str) -> User:
        """FR-01: register a user with a unique email."""
        clean_name = _clean_name("name", name)
        normalised = (email or "").strip().lower()
        if len(normalised) > MAX_EMAIL_LEN or not EMAIL_RE.match(normalised):
            raise InvalidEmailError("email", "is not a valid email address")
        if self._users.find_by_email(normalised) is not None:
            raise DuplicateEmailError(f"email {normalised} is already registered")
        user = self._users.add(clean_name, normalised, self._clock.now())
        logger.info("user registered id=%s", user.id)
        return user

    def get(self, user_id: int) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFoundError(f"user {user_id} not found")
        return user


class GroupService:
    def __init__(
        self,
        groups: GroupRepository,
        users: UserRepository,
        ledger: LedgerReader,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._groups = groups
        self._users = users
        self._ledger = ledger
        self._uow = uow
        self._clock = clock

    # --- queries ---------------------------------------------------------
    def get(self, group_id: int) -> Group:
        group = self._groups.get(group_id)
        if group is None:
            raise GroupNotFoundError(f"group {group_id} not found")
        return group

    def members(self, group_id: int, actor_id: int) -> list[int]:
        self.require_member(group_id, actor_id)
        return self._groups.member_ids(group_id)

    def require_member(self, group_id: int, user_id: int) -> Group:
        group = self.get(group_id)
        if not self._groups.is_member(group_id, user_id):
            raise NotGroupMemberError(f"user {user_id} is not a member of group {group_id}")
        return group

    def require_admin(self, group_id: int, user_id: int) -> Group:
        group = self.require_member(group_id, user_id)
        if group.admin_id != user_id:
            raise NotGroupAdminError(f"user {user_id} is not the admin of group {group_id}")
        return group

    # --- commands --------------------------------------------------------
    def create_group(self, name: str, creator_id: int) -> Group:
        """FR-02: the creator becomes admin and first member."""
        clean_name = _clean_name("name", name)
        if self._users.get(creator_id) is None:
            raise UserNotFoundError(f"user {creator_id} not found")
        now = self._clock.now()
        group = self._groups.add(clean_name, creator_id, now)
        self._groups.add_member(group.id, creator_id, now)
        logger.info("group created id=%s admin=%s", group.id, creator_id)
        return group

    def add_member(self, group_id: int, actor_id: int, user_id: int) -> None:
        """FR-03: only the admin adds members."""
        with self._uow.for_group(group_id):
            self.require_admin(group_id, actor_id)
            if self._users.get(user_id) is None:
                raise UserNotFoundError(f"user {user_id} not found")
            if self._groups.is_member(group_id, user_id):
                raise AlreadyMemberError(f"user {user_id} is already in group {group_id}")
            self._groups.add_member(group_id, user_id, self._clock.now())

    def remove_member(self, group_id: int, actor_id: int, user_id: int) -> None:
        """FR-03: only the admin removes; not the admin; not with a non-zero balance."""
        with self._uow.for_group(group_id):
            group = self.require_admin(group_id, actor_id)
            if not self._groups.is_member(group_id, user_id):
                raise NotGroupMemberError(f"user {user_id} is not a member of group {group_id}")
            if user_id == group.admin_id:
                raise CannotRemoveAdminError("the admin cannot be removed from the group")
            balance = self._ledger.balance_of(group_id, user_id)
            if not balance.is_zero():
                raise MemberHasBalanceError(
                    f"user {user_id} has a balance of {balance.to_rupees_str()} PKR"
                )
            self._groups.remove_member(group_id, user_id)

    def ensure_can_record_expenses(self, group_id: int) -> None:
        """FR-02: a group needs at least 2 members before expenses are recorded."""
        if len(self._groups.member_ids(group_id)) < MIN_MEMBERS_FOR_EXPENSES:
            raise GroupTooSmallError(
                "group", f"needs at least {MIN_MEMBERS_FOR_EXPENSES} members before expenses"
            )
