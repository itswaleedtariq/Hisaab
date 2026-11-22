-- Hisaab schema, version 1. All money columns are integer paisa (1 PKR = 100 paisa).

CREATE TABLE users (
   id         INTEGER PRIMARY KEY,
   name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
   email      TEXT NOT NULL UNIQUE,
   created_at TEXT NOT NULL
);

CREATE TABLE groups (
   id         INTEGER PRIMARY KEY,
   name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
   admin_id   INTEGER NOT NULL REFERENCES users(id),
   created_at TEXT NOT NULL
);

CREATE TABLE memberships (
   group_id    INTEGER NOT NULL REFERENCES groups(id),
   user_id     INTEGER NOT NULL REFERENCES users(id),
   joined_at   TEXT NOT NULL,
   PRIMARY KEY (group_id, user_id)
);

CREATE TABLE expenses (
   id              INTEGER PRIMARY KEY,
   group_id        INTEGER NOT NULL REFERENCES groups(id),
   payer_id        INTEGER NOT NULL REFERENCES users(id),
   amount_paisa    INTEGER NOT NULL CHECK (amount_paisa > 0 AND amount_paisa <= 1000000000),
   split_type      TEXT NOT NULL CHECK (split_type IN ('equal','exact','percent','shares')),
   category        TEXT,
   description     TEXT,
   spent_on        TEXT NOT NULL,
   status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','voided')),
   idempotency_key TEXT UNIQUE,
   created_by      INTEGER NOT NULL REFERENCES users(id),
   created_at      TEXT NOT NULL
);

CREATE TABLE expense_shares (
   expense_id    INTEGER NOT NULL REFERENCES expenses(id),
   user_id       INTEGER NOT NULL REFERENCES users(id),
   amount_paisa  INTEGER NOT NULL CHECK (amount_paisa >= 0),
   PRIMARY KEY (expense_id, user_id)
);

-- Append-only. Positive amount = the group owes this user.
CREATE TABLE ledger_entries (
   id           INTEGER PRIMARY KEY,
   group_id     INTEGER NOT NULL REFERENCES groups(id),
   user_id      INTEGER NOT NULL REFERENCES users(id),
   amount_paisa INTEGER NOT NULL,
   source_type  TEXT NOT NULL CHECK (source_type IN ('expense','void','settlement')),
   source_id    INTEGER NOT NULL,
   created_at   TEXT NOT NULL
);
CREATE INDEX idx_ledger_group_user ON ledger_entries (group_id, user_id);

CREATE TABLE settlements (
   id            INTEGER PRIMARY KEY,
   group_id      INTEGER NOT NULL REFERENCES groups(id),
   from_user_id  INTEGER NOT NULL REFERENCES users(id),
   to_user_id    INTEGER NOT NULL REFERENCES users(id),
   amount_paisa  INTEGER NOT NULL CHECK (amount_paisa > 0),
   created_at    TEXT NOT NULL,
   CHECK (from_user_id <> to_user_id)
);

CREATE TABLE report_jobs (
   id           INTEGER PRIMARY KEY,
   group_id     INTEGER NOT NULL REFERENCES groups(id),
   period       TEXT NOT NULL,          -- 'YYYY-MM'
   format       TEXT NOT NULL CHECK (format IN ('csv','html')),
   status       TEXT NOT NULL CHECK (status IN ('pending','running','done','failed')),
   file_path    TEXT,
   error        TEXT,
   requested_by INTEGER NOT NULL REFERENCES users(id),
   created_at   TEXT NOT NULL,
   finished_at  TEXT
);

CREATE TABLE schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version (version) VALUES (1);
