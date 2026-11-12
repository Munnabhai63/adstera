-- Migration 001: Initial Phase 3 SQLite tables

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS p3_sessions (
    session_id      TEXT PRIMARY KEY,
    correlation_id  TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    mode            TEXT NOT NULL,
    domain          TEXT NOT NULL,
    ip_address      TEXT NOT NULL DEFAULT '',
    subnet_24       TEXT NOT NULL DEFAULT '',
    subnet_20       TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'started',
    started_at      REAL NOT NULL,
    ended_at        REAL DEFAULT NULL,
    dwell_seconds   REAL NOT NULL DEFAULT 0.0,
    error           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS p3_decisions_rewards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    domain          TEXT NOT NULL,
    slot_type       TEXT NOT NULL,
    action          TEXT NOT NULL,
    executed_touch  INTEGER NOT NULL DEFAULT 0,
    bbox_json       TEXT NOT NULL DEFAULT 'null',
    a4_source       TEXT NOT NULL DEFAULT 'none',
    a4_confidence   REAL NOT NULL DEFAULT 0.0,
    a2_severity     TEXT NOT NULL DEFAULT 'OK',
    safe_mode       INTEGER NOT NULL DEFAULT 0,
    rpm             REAL NOT NULL DEFAULT 0.0,
    ctr             REAL NOT NULL DEFAULT 0.0,
    reward_value    REAL NOT NULL DEFAULT 0.0,
    reason          TEXT NOT NULL DEFAULT '',
    ts              REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS p3_cgnat_slots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    ip_address      TEXT NOT NULL,
    subnet_24       TEXT NOT NULL,
    subnet_20       TEXT NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1,
    acquired_at     REAL NOT NULL,
    released_at     REAL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS p3_forecasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon_days    INTEGER NOT NULL,
    sample_count    INTEGER NOT NULL,
    method          TEXT NOT NULL,
    p10_revenue     REAL NOT NULL,
    p50_revenue     REAL NOT NULL,
    p90_revenue     REAL NOT NULL,
    p10_ecpm        REAL NOT NULL,
    p50_ecpm        REAL NOT NULL,
    p90_ecpm        REAL NOT NULL,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS p3_farm_devices (
    device_id            TEXT PRIMARY KEY,
    usb_port             TEXT NOT NULL DEFAULT '',
    cdp_port             INTEGER NOT NULL DEFAULT 0,
    b1_port              INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'healthy',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    quarantined_until    REAL NOT NULL DEFAULT 0.0,
    total_sessions       INTEGER NOT NULL DEFAULT 0,
    total_clicks         INTEGER NOT NULL DEFAULT 0,
    last_seen_at         REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_p3_sessions_device ON p3_sessions(device_id, started_at);
CREATE INDEX IF NOT EXISTS idx_p3_rewards_session ON p3_decisions_rewards(session_id);
CREATE INDEX IF NOT EXISTS idx_p3_cgnat_24 ON p3_cgnat_slots(subnet_24, acquired_at);
CREATE INDEX IF NOT EXISTS idx_p3_cgnat_20 ON p3_cgnat_slots(subnet_20, acquired_at);
CREATE INDEX IF NOT EXISTS idx_p3_cgnat_active ON p3_cgnat_slots(device_id, active);
