-- GramSathi relational schema (SQLite dialect; portable to MySQL/PostgreSQL with minor type edits)
-- Replaces the old Firestore collections with normalised tables, foreign keys and indexes.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    mobile        TEXT    NOT NULL,
    age           INTEGER CHECK (age BETWEEN 0 AND 120),
    role          TEXT    NOT NULL DEFAULT 'citizen' CHECK (role IN ('citizen', 'admin')),
    address       TEXT    NOT NULL DEFAULT '',
    village       TEXT    NOT NULL DEFAULT '',
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS ration_cards (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_no           TEXT    NOT NULL UNIQUE,
    card_type         TEXT    NOT NULL CHECK (card_type IN ('APL', 'BPL', 'AAY')),
    validity_start    TEXT    NOT NULL,
    validity_end      TEXT    NOT NULL,
    distribution_point TEXT   NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'expired')),
    last_distribution TEXT,
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_ration_user ON ration_cards(user_id);

CREATE TABLE IF NOT EXISTS ration_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id  INTEGER NOT NULL REFERENCES ration_cards(id) ON DELETE CASCADE,
    name     TEXT    NOT NULL,
    quantity REAL    NOT NULL CHECK (quantity >= 0),
    unit     TEXT    NOT NULL DEFAULT 'kg'
);

CREATE TABLE IF NOT EXISTS anganwadi_centers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    address    TEXT NOT NULL,
    phone      TEXT NOT NULL DEFAULT '',
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL,
    services   TEXT NOT NULL DEFAULT '[]',   -- JSON array
    open_time  TEXT NOT NULL DEFAULT '09:00',
    close_time TEXT NOT NULL DEFAULT '16:00'
);

CREATE TABLE IF NOT EXISTS anganwadi_beneficiaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    center_id       INTEGER NOT NULL REFERENCES anganwadi_centers(id) ON DELETE CASCADE,
    child_name      TEXT    NOT NULL,
    age_group       TEXT    NOT NULL CHECK (age_group IN ('0-6', '6-14')),
    status          TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    enrollment_date TEXT    NOT NULL,
    last_visit      TEXT
);
CREATE INDEX IF NOT EXISTS idx_beneficiary_user ON anganwadi_beneficiaries(user_id);
CREATE INDEX IF NOT EXISTS idx_beneficiary_center ON anganwadi_beneficiaries(center_id);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    doc_type    TEXT    NOT NULL CHECK (doc_type IN ('birth_certificate', 'bonafide_certificate')),
    status      TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    data        TEXT    NOT NULL,            -- JSON form payload
    ai_review   TEXT,                        -- JSON: risk score, flags, recommendation
    admin_note  TEXT    NOT NULL DEFAULT '',
    reviewed_by INTEGER REFERENCES users(id),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status, created_at);

CREATE TABLE IF NOT EXISTS news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL,
    title_hi    TEXT    NOT NULL DEFAULT '',
    description_hi TEXT NOT NULL DEFAULT '',
    title_mr    TEXT    NOT NULL DEFAULT '',
    description_mr TEXT NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT 'general' CHECK (category IN ('scheme', 'deadline', 'alert', 'health', 'general')),
    priority    INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    active      INTEGER NOT NULL DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_news_active ON news(active, priority DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS water_connections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_no TEXT    NOT NULL UNIQUE,
    status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive'))
);
CREATE INDEX IF NOT EXISTS idx_water_user ON water_connections(user_id);

CREATE TABLE IF NOT EXISTS water_bills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL REFERENCES water_connections(id) ON DELETE CASCADE,
    period        TEXT    NOT NULL,          -- e.g. 2026-09
    amount        REAL    NOT NULL CHECK (amount >= 0),
    due_date      TEXT    NOT NULL,
    paid          INTEGER NOT NULL DEFAULT 0,
    paid_on       TEXT,
    UNIQUE (connection_id, period)
);
CREATE INDEX IF NOT EXISTS idx_water_bills_due ON water_bills(paid, due_date);

CREATE TABLE IF NOT EXISTS properties (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_no  TEXT    NOT NULL UNIQUE,
    address      TEXT    NOT NULL,
    area_sqft    REAL    NOT NULL CHECK (area_sqft > 0),
    value        REAL    NOT NULL CHECK (value >= 0),
    tax_rate     REAL    NOT NULL CHECK (tax_rate >= 0),   -- percent per year
    annual_tax   REAL    NOT NULL,
    due_date     TEXT    NOT NULL,
    last_paid    TEXT,
    paid         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_properties_user ON properties(user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       TEXT    NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT    NOT NULL,
    source     TEXT    NOT NULL DEFAULT 'rules',   -- 'claude' or 'rules'
    created_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id   INTEGER REFERENCES users(id),
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- Rozgar local employment marketplace
CREATE TABLE IF NOT EXISTS rozgar_profiles (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  profile_type TEXT NOT NULL DEFAULT 'worker' CHECK(profile_type IN ('worker','employer')),
  headline TEXT NOT NULL DEFAULT '', skills TEXT NOT NULL DEFAULT '[]', experience_years REAL NOT NULL DEFAULT 0,
  education TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', bio TEXT NOT NULL DEFAULT '',
  phone_public INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS rozgar_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, employer_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, company TEXT NOT NULL, description TEXT NOT NULL, skills TEXT NOT NULL DEFAULT '[]',
  location TEXT NOT NULL, job_type TEXT NOT NULL DEFAULT 'Full-time', salary_min REAL, salary_max REAL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','published','rejected','closed')),
  scam_score INTEGER NOT NULL DEFAULT 0, scam_flags TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_rozgar_jobs_status ON rozgar_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rozgar_jobs_employer ON rozgar_jobs(employer_id);
CREATE TABLE IF NOT EXISTS rozgar_applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES rozgar_jobs(id) ON DELETE CASCADE,
  worker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, cover_note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted','shortlisted','rejected','hired')),
  match_score INTEGER NOT NULL DEFAULT 0, match_reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), UNIQUE(job_id, worker_id)
);
CREATE INDEX IF NOT EXISTS idx_rozgar_app_job ON rozgar_applications(job_id, match_score DESC);
CREATE INDEX IF NOT EXISTS idx_rozgar_app_worker ON rozgar_applications(worker_id, created_at DESC);
