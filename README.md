# Hisaab

Hisaab is a group expense splitter. People in a shared flat, a trip or an office lunch group record who paid for what, choose how each expense is split, and Hisaab keeps everyone's balance and suggests the fewest payments needed to settle up.

This is our semester project for SE423 (Software Construction and Development) and SE431 (Software Quality Assurance). Both courses grade this same repository.

## Team

| Member | Reg no | Modules (SE423) | SE431 lead at M1 |
| --- | --- | --- | --- |
| Waleed Tariq | 2023751 | Users and Groups, Reports | Quality requirements, RTM |
| Muhammad Abdullah | 2023341 | Expenses, Split Engine | Cost of quality, standards |
| Abdullah Rashid | 2023043 | Ledger and Settlement | SQAP outline, risk register |

Team lead and integrator rotates each milestone:

| Milestone | SE423 lead | SE431 lead |
| --- | --- | --- |
| M1 | Waleed Tariq | Abdullah Rashid |
| M2 | Muhammad Abdullah | Muhammad Abdullah |
| M3 | Abdullah Rashid | Waleed Tariq |

## What it does

- Register users and create groups with an admin
- Record expenses in PKR (stored as integer paisa, never floats)
- Split an expense equally, by exact amounts, by percentage or by shares
- Keep balances correct even when several members post at the same time
- Void a wrong expense without deleting history
- Suggest a settlement plan with at most n-1 payments for n members
- Generate monthly statements and CSV exports in the background

Each feature has a requirement ID (FR-01 to FR-16, QR-01 to QR-17). The full list is in `docs/qa/rtm.xlsx`.

## Tech stack

- Python 3.12
- FastAPI for the HTTP API
- SQLite (WAL mode) for storage
- pytest, pytest-cov and Hypothesis for testing
- ruff for linting
- GitHub Actions for CI

## Getting started

You need Python 3.12 and Git.

```bash
git clone https://github.com/<owner>/hisaab.git
cd hisaab
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
pytest
```

Before your first commit, make sure git uses the same email as your GitHub account, or your commits will not be counted as yours:

```bash
git config --global user.name "Your Full Name"
git config --global user.email "your-github-email@example.com"
```

## Running tests and lint

```bash
pytest                      # whole suite with coverage
pytest tests/unit           # fast unit tests
pytest tests/concurrency    # thread-safety tests
ruff check .                # lint
```

Coverage is printed in the terminal and saved to `coverage.xml`. CI runs the same commands on every push.

## Running the API

The API layer arrives in M2. Once it is in:

```bash
uvicorn hisaab.api.app:app --reload
```

Then open http://127.0.0.1:8000/docs.

## Project layout

```
hisaab/
  domain/        Money, Expense, Share and the shared exception classes (errors.py)
  users/         Users and Groups
  expenses/      Expenses (ExpenseService, ExpenseBuilder)
  splitting/     Split Engine (split strategies and their factory)
  ledger/        Ledger and Settlement (balances, locks, settlement planner)
  reports/       Reports (background worker, CSV export)
  events/        In-process event bus
  persistence/   SQLite adapters and schema.sql
  api/           FastAPI routes and error mapping
tests/
  unit/          fast tests with in-memory repositories
  integration/   tests against a temporary SQLite file
  concurrency/   multi-thread tests
  contracts/     tests every implementation of an interface must pass
docs/
  se423/         SE423 milestone reports
  se431/         SE431 milestone reports
  design/        diagram sources
  qa/            RTM, risk register, cost of quality
```

## How we work

### Branches

| Branch | Used for |
| --- | --- |
| `main` | Milestone baselines only, tagged `m1-baseline`, `m2-baseline`, `m3-final` |
| `develop` | Integration. Everything merges here first |
| `feature/<module>-<topic>` | New code, e.g. `feature/split-equal` |
| `docs/<topic>` | Reports and QA documents |
| `fix/<short-name>` | Defects from review, inspection or CI |

Full rules are in [BRANCHING.md](BRANCHING.md).

### Everyday workflow

```bash
git checkout develop
git pull
git checkout -b feature/split-equal

# write a failing test first, then:
git add tests/...
git commit -m "test(split): equal split rules for FR-05"
git push -u origin feature/split-equal

# write the code until the test passes, then:
git add hisaab/
git commit -m "feat(split): EqualSplit with remainder to payer"
git push
```

Then open a pull request into `develop` on GitHub and ask a teammate to review it.

### Rules

- No direct pushes to `main` or `develop`. Always use a pull request.
- Nobody approves or merges their own pull request.
- Merge with "Create a merge commit". Squash and rebase are turned off so our test-first commits stay visible.
- Each pull request names the requirement ID (FR-xx or QR-xx) or the defect/CAPA ID it addresses.
- Commit messages follow `type(module): what changed`. Types: `test`, `feat`, `refactor`, `fix`, `docs`, `ci`, `chore`.
- A red CI build gets fixed before more feature work goes on that branch.
- Everyone must be able to explain every line they push. Any AI help is recorded in [AI_USAGE_LOG.md](AI_USAGE_LOG.md).

## Milestones

| Milestone | Week | SE423 | SE431 |
| --- | --- | --- | --- |
| M1 | 6 | Proposal, OOD and pattern plan | Quality requirements, RTM v1, SQAP outline, risk register |
| M2 | 10 | Working architecture, patterns, concurrency, test baseline | Fagan inspection, static analysis, V&V plan, test design, SCM evidence |
| M3 | 13 | Final system, 60%+ coverage, refactoring, CI, demo | Final SQAP, test execution, GQM, final risk register, audit |
