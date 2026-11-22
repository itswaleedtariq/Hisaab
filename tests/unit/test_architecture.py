"""Module-boundary checks (DEF-04): Ledger, Reports and Users must not depend on
the Expenses service module. Shared contracts live with the module that owns them."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "hisaab"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}


@pytest.mark.parametrize("package", ["ledger", "reports", "users"])
def test_package_does_not_import_expenses_service(package):
    for source in (PACKAGE / package).glob("*.py"):
        assert "hisaab.expenses.service" not in imported_modules(source), source.name
