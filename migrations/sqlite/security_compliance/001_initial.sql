-- Compliance automation tables
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    name TEXT,
    framework TEXT,
    policy_type TEXT,
    control_id TEXT,
    description TEXT,
    requirements TEXT,
    implementation_guidance TEXT,
    testing_procedures TEXT,
    evidence_requirements TEXT,
    risk_level TEXT,
    mandatory BOOLEAN,
    frequency_days INTEGER,
    owner TEXT,
    created_at TEXT,
    updated_at TEXT,
    version TEXT
);

CREATE TABLE IF NOT EXISTS violations (
    violation_id TEXT PRIMARY KEY,
    policy_id TEXT,
    framework TEXT,
    severity TEXT,
    title TEXT,
    description TEXT,
    affected_systems TEXT,
    detected_at TEXT,
    root_cause TEXT,
    remediation_plan TEXT,
    remediation_deadline TEXT,
    status TEXT,
    assigned_to TEXT,
    evidence TEXT,
    business_impact TEXT,
    resolution_notes TEXT,
    resolved_at TEXT,
    FOREIGN KEY (policy_id) REFERENCES policies (policy_id)
);

CREATE TABLE IF NOT EXISTS audit_trail (
    audit_id TEXT PRIMARY KEY,
    event_type TEXT,
    timestamp TEXT,
    user_id TEXT,
    source_system TEXT,
    object_type TEXT,
    object_id TEXT,
    action TEXT,
    details TEXT,
    ip_address TEXT,
    user_agent TEXT,
    session_id TEXT,
    integrity_hash TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    policy_id TEXT,
    control_id TEXT,
    evidence_type TEXT,
    title TEXT,
    description TEXT,
    file_path TEXT,
    content TEXT,
    metadata TEXT,
    collected_at TEXT,
    collected_by TEXT,
    hash_value TEXT,
    retention_days INTEGER,
    FOREIGN KEY (policy_id) REFERENCES policies (policy_id)
);

CREATE INDEX IF NOT EXISTS idx_violations_policy_id ON violations(policy_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_trail(timestamp);
CREATE INDEX IF NOT EXISTS idx_evidence_policy_id ON evidence(policy_id);
