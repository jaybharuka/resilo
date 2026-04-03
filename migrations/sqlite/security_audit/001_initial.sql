-- Audit logging system tables
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    details TEXT NOT NULL,
    compliance_frameworks TEXT,
    tags TEXT,
    correlation_id TEXT,
    parent_event_id TEXT,
    checksum TEXT NOT NULL,
    archived BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_ip TEXT NOT NULL,
    target_ip TEXT,
    user_id TEXT,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    threat_indicators TEXT,
    geolocation TEXT,
    details TEXT,
    mitre_tactics TEXT,
    remediation_actions TEXT
);

CREATE TABLE IF NOT EXISTS compliance_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    violation_id TEXT NOT NULL UNIQUE,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    framework TEXT NOT NULL,
    event_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS forensic_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    analyst TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    event_ids TEXT NOT NULL,
    filters TEXT NOT NULL,
    findings TEXT,
    evidence TEXT,
    status TEXT NOT NULL,
    tags TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_security_ip ON security_events(source_ip);
CREATE INDEX IF NOT EXISTS idx_security_timestamp ON security_events(timestamp);
