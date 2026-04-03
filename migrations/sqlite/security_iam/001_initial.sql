-- IAM monitoring tables
CREATE TABLE IF NOT EXISTS access_events (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT,
    user_id TEXT,
    username TEXT,
    access_type TEXT,
    resource TEXT,
    source_ip TEXT,
    authentication_method TEXT,
    access_status TEXT,
    risk_level TEXT,
    anomaly_score REAL,
    is_suspicious INTEGER,
    context TEXT
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    email TEXT,
    account_type TEXT,
    creation_date TEXT,
    last_login TEXT,
    login_count INTEGER,
    failed_login_count INTEGER,
    mfa_enabled INTEGER,
    account_locked INTEGER,
    is_active INTEGER,
    risk_score REAL,
    profile_data TEXT
);

CREATE TABLE IF NOT EXISTS privilege_escalations (
    escalation_id TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    escalation_type TEXT,
    detection_timestamp TEXT,
    risk_level TEXT,
    confidence_score REAL,
    investigated INTEGER,
    false_positive INTEGER,
    details TEXT
);

CREATE TABLE IF NOT EXISTS access_anomalies (
    anomaly_id TEXT PRIMARY KEY,
    user_id TEXT,
    username TEXT,
    anomaly_type TEXT,
    description TEXT,
    detection_timestamp TEXT,
    anomaly_score REAL,
    risk_level TEXT,
    requires_investigation INTEGER,
    details TEXT
);
