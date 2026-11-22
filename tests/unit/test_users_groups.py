"""Users and Groups (FR-01 to FR-03). Owner: Waleed Tariq.

Test case ids (TC-BB-xx, TC-WB-xx) match the SE431 M2 test design.
"""

import pytest

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
from hisaab.domain.models import LedgerEntry, LedgerSource
from hisaab.domain.money import Money
from tests.conftest import NOW


@pytest.fixture
def users(people):
    return people.users


# --- FR-01: EP on email, BVA on name length ---------------------------------
@pytest.mark.parametrize(
    "email",
    [
        pytest.param("ali.example.com", id="TC-BB-02 no @"),
        pytest.param("ali@example", id="TC-BB-03 no top-level domain"),
        pytest.param("ali @example.com", id="TC-BB-04 contains a space"),
        pytest.param("", id="TC-BB-05 empty"),
        pytest.param("a" * 250 + "@x.com", id="TC-BB-06 longer than 254"),
    ],
)
def test_register_rejects_invalid_email(users, email):
    with pytest.raises(InvalidEmailError):
        users.register("Zara", email)


def test_register_valid_email_is_normalised(users):
    """TC-BB-01: valid email class."""
    user = users.register("  Zara  ", " Zara@Example.COM ")
    assert (user.name, user.email) == ("Zara", "zara@example.com")
    assert users.get(user.id) == user


def test_register_rejects_duplicate_email_case_insensitive(users):
    """TC-BB-07: duplicate email class."""
    with pytest.raises(DuplicateEmailError):
        users.register("Ali Two", "ALI@example.com")


@pytest.mark.parametrize(
    ("length", "ok"),
    [
        pytest.param(0, False, id="TC-BB-08 name length 0"),
        pytest.param(1, True, id="TC-BB-09 name length 1"),
        pytest.param(80, True, id="TC-BB-10 name length 80"),
        pytest.param(81, False, id="TC-BB-11 name length 81"),
    ],
)
def test_name_length_boundaries(users, length, ok):
    if ok:
        assert len(users.register("n" * length, f"u{length}@example.com").name) == length
    else:
        with pytest.raises(ValidationError):
            users.register("n" * length, f"u{length}@example.com")


def test_get_unknown_user(users):
    with pytest.raises(UserNotFoundError):
        users.get(99)


# --- FR-02 ------------------------------------------------------------------
def test_creator_becomes_admin_and_member(people):
    zara = people.users.register("Zara", "zara@example.com").id
    group = people.groups.create_group("Office lunch", zara)
    assert group.admin_id == zara
    assert people.groups.members(group.id, zara) == [zara]


def test_create_group_needs_known_user_and_valid_name(people):
    with pytest.raises(UserNotFoundError):
        people.groups.create_group("Ghost group", 42)
    with pytest.raises(ValidationError):
        people.groups.create_group("   ", people.ali)


@pytest.mark.parametrize(
    ("members", "ok"),
    [
        pytest.param(1, False, id="TC-BB-12 one member"),
        pytest.param(2, True, id="TC-BB-13 two members"),
    ],
)
def test_minimum_members_before_expenses(people, members, ok):
    group = people.groups.create_group("Pair", people.ali)
    if members == 2:
        people.groups.add_member(group.id, people.ali, people.sara)
    if ok:
        people.groups.ensure_can_record_expenses(group.id)
    else:
        with pytest.raises(GroupTooSmallError):
            people.groups.ensure_can_record_expenses(group.id)


# --- FR-03 add member ---------------------------------------------------------
def test_only_admin_adds_members(people):
    zara = people.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupAdminError):
        people.groups.add_member(people.group_id, people.sara, zara)
    people.groups.add_member(people.group_id, people.ali, zara)
    assert zara in people.groups.members(people.group_id, people.ali)


def test_add_member_errors(people):
    with pytest.raises(AlreadyMemberError):
        people.groups.add_member(people.group_id, people.ali, people.sara)
    with pytest.raises(UserNotFoundError):
        people.groups.add_member(people.group_id, people.ali, 999)
    with pytest.raises(GroupNotFoundError):
        people.groups.add_member(999, people.ali, people.sara)


def test_non_member_cannot_list_members(people):
    zara = people.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        people.groups.members(people.group_id, zara)


# --- FR-03 remove_member: basis paths (SE431 M2, white-box design) -------------
def give_balance(people, user_id, paisa):
    people.ledger.append([
        LedgerEntry(people.group_id, user_id, Money(paisa), LedgerSource.EXPENSE, 1, NOW),
        LedgerEntry(people.group_id, people.ali, Money(-paisa), LedgerSource.EXPENSE, 1, NOW),
    ])


def test_tc_wb_01_target_not_a_member(people):
    zara = people.users.register("Zara", "zara@example.com").id
    with pytest.raises(NotGroupMemberError):
        people.groups.remove_member(people.group_id, people.ali, zara)


def test_tc_wb_02_admin_cannot_be_removed(people):
    with pytest.raises(CannotRemoveAdminError):
        people.groups.remove_member(people.group_id, people.ali, people.ali)


def test_tc_wb_03_member_with_balance_cannot_be_removed(people):
    give_balance(people, people.bilal, -10000)
    with pytest.raises(MemberHasBalanceError):
        people.groups.remove_member(people.group_id, people.ali, people.bilal)


def test_tc_wb_04_member_at_zero_is_removed(people):
    people.groups.remove_member(people.group_id, people.ali, people.bilal)
    assert people.bilal not in people.groups.members(people.group_id, people.ali)


def test_remove_member_requires_admin(people):
    """Exception path inside require_admin (called function), not a basis path here."""
    with pytest.raises(NotGroupAdminError):
        people.groups.remove_member(people.group_id, people.sara, people.bilal)
