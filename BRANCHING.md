# Branching, review and merge rules

These rules apply to all three of us and to every change in this repository. They are part of our SCM practice for SE431, so the repository history is our evidence that we followed them.

## Branches

| Branch | Purpose | Created from | Merges into | Who merges |
| --- | --- | --- | --- | --- |
| `main` | Milestone baselines only | - | - | That milestone's team lead |
| `develop` | Integration branch, always green | `main` | `main` at the end of a milestone | That milestone's team lead |
| `feature/<module>-<topic>` | New code, e.g. `feature/split-equal` | `develop` | `develop` | A reviewer, never the author |
| `docs/<topic>` | Reports and QA documents, e.g. `docs/se431-m1` | `develop` | `develop` | A reviewer, never the author |
| `fix/<short-name>` | Defects found in review, inspection, static analysis or CI | `develop` | `develop` | A reviewer, never the author |

Module names used in branch names and commit messages: `users`, `expenses`, `split`, `ledger`, `reports`, `events`, `persistence`, `api`, `qa`, `se423`, `se431`.

## Rules

1. Nobody pushes directly to `main` or `develop`. Both are protected on GitHub.
2. Every change reaches `develop` through a pull request.
3. A pull request into `develop` needs all of these before it can be merged:
   - the CI check `test` is green
   - one approving review from a member who is not the author
   - a description naming the requirement ID (FR-xx or QR-xx) or the defect/CAPA ID it addresses
4. Pull requests are merged with **Create a merge commit**. Squash merging and rebase merging are turned off in the repository settings, so the red, green and refactor commits on each branch stay in history.
5. One branch is for one piece of work. Keep branches short-lived and delete them after merging.
6. A red CI build is fixed before more feature work continues on that branch. The exception is the deliberate red commit at the start of a TDD cycle.
7. Never rewrite history that has been pushed. No `git push --force` on shared branches.

## TDD commit order on a feature branch

Every behaviour starts as a failing test, committed on its own:

```
test(ledger): concurrent posts keep group balance at zero      <- red, CI fails on purpose
feat(ledger): guard posting with per-group lock                 <- green
refactor(ledger): move lock lookup into LockRegistry            <- still green
```

Do not put the test and the code in the same commit. The instructor checks this order in `git log`.

## Commit messages

```
<type>(<module>): <what changed, in present tense>
```

| Type | Use for |
| --- | --- |
| `test` | Adding or changing tests (the red step) |
| `feat` | New behaviour that makes tests pass (the green step) |
| `refactor` | Restructuring without changing behaviour |
| `fix` | Fixing a defect; mention the defect or CAPA ID |
| `docs` | Reports, README, QA documents |
| `ci` | Changes to the GitHub Actions workflow |
| `chore` | Setup, dependencies, housekeeping |

Examples:

```
test(users): registration rejects duplicate email (FR-01)
feat(split): PercentageSplit validates total of 100.00 (FR-07)
fix(ledger): release lock when append fails (DEF-004)
docs(qa): update risk register after M2 inspection
```

## Pull request checklist

The author fills this in the PR description:

- [ ] Requirement or defect ID: ______
- [ ] Tests were written before the code (red commit is in this branch)
- [ ] `pytest` passes locally
- [ ] `ruff check .` is clean
- [ ] RTM updated if a requirement's status changed

The reviewer checks:

- [ ] The code does what the requirement says
- [ ] Tests cover normal cases, boundary values and error cases
- [ ] No bare `except`, and errors come from `hisaab/domain/errors.py`
- [ ] No money stored as float
- [ ] Names and structure match the design (patterns, SOLID decisions)
- [ ] The author can explain the change if asked

Review comments must be answered (fixed or replied to) before merging.

## Baselines and tags

At the end of each milestone the team lead:

1. Opens a pull request from `develop` into `main`.
2. Gets one approval and merges it.
3. Tags the merge commit:

```bash
git checkout main
git pull
git tag m1-baseline
git push origin m1-baseline
```

| Tag | When |
| --- | --- |
| `m1-baseline` | End of Milestone 1 (Week 6) |
| `m2-baseline` | End of Milestone 2 (Week 10) |
| `m3-final` | Final submission (Week 13) |

A baseline tag is never moved or deleted. A fix found after a baseline goes into the next one. All SE431 quality work for a milestone (inspection, static analysis, test execution) is run against that milestone's tagged baseline.

## Everyday commands

```bash
# start new work
git checkout develop
git pull
git checkout -b feature/split-equal

# save and share
git add <files>
git commit -m "test(split): equal split rules for FR-05"
git push -u origin feature/split-equal    # first push of the branch
git push                                   # later pushes

# after your PR is merged
git checkout develop
git pull
git branch -d feature/split-equal
```

If GitHub says your branch has conflicts with `develop`:

```bash
git checkout feature/split-equal
git pull origin develop
# fix the files marked with <<<<<<< and >>>>>>>, then:
git add <fixed files>
git commit
git push
```

## Before you push

- `pytest` passes locally (except on a deliberate red commit)
- `ruff check .` is clean
- `git config user.email` matches the email on your GitHub account, so the commit is credited to you

## Repository settings (set once by the M1 lead)

| Setting | Value |
| --- | --- |
| Default branch | `develop` |
| Allow merge commits | On |
| Allow squash merging | Off |
| Allow rebase merging | Off |
| Automatically delete head branches | On |
| Protection on `main` and `develop` | Require pull request, 1 approval, status check `test` |
