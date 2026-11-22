"""Exception hierarchy shared by every Hisaab module.

Every module raises one of these. The API layer (hisaab/api/errors.py) is the
only place that turns them into HTTP responses.
"""


class HisaabError(Exception):
    """Root of all Hisaab errors."""


# --- 422: the request is well formed but breaks a business rule -------------
class ValidationError(HisaabError):
    """Input breaks a business rule. The message names the field and the rule."""

    def __init__(self, field: str, rule: str) -> None:
        self.field = field
        self.rule = rule
        super().__init__(f"{field}: {rule}")


class InvalidAmountError(ValidationError):
    pass


class InvalidSplitError(ValidationError):
    pass


class InvalidExpenseError(ValidationError):
    pass


class InvalidEmailError(ValidationError):
    pass


class InvalidSettlementError(ValidationError):
    pass


class GroupTooSmallError(ValidationError):
    pass


# --- 404 -------------------------------------------------------------------
class NotFoundError(HisaabError):
    pass


class UserNotFoundError(NotFoundError):
    pass


class GroupNotFoundError(NotFoundError):
    pass


class ExpenseNotFoundError(NotFoundError):
    pass


class ReportJobNotFoundError(NotFoundError):
    pass


# --- 403 -------------------------------------------------------------------
class PermissionDeniedError(HisaabError):
    pass


class NotGroupMemberError(PermissionDeniedError):
    pass


class NotGroupAdminError(PermissionDeniedError):
    pass


# --- 409 -------------------------------------------------------------------
class ConflictError(HisaabError):
    pass


class DuplicateEmailError(ConflictError):
    pass


class AlreadyMemberError(ConflictError):
    pass


class MemberHasBalanceError(ConflictError):
    pass


class CannotRemoveAdminError(ConflictError):
    pass


class ExpenseAlreadyVoidedError(ConflictError):
    pass


# --- 503 -------------------------------------------------------------------
class ConcurrencyError(HisaabError):
    pass


class LockTimeoutError(ConcurrencyError):
    pass


class NestedGroupLockError(ConcurrencyError):
    """Raised if code tries to hold two group locks at once (deadlock guard)."""


# --- 500 -------------------------------------------------------------------
class PersistenceError(HisaabError):
    """Wraps sqlite3.Error. Details are logged, never shown to the user."""
