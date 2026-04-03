-- Incident response tables
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    incident_type TEXT,
    severity TEXT,
    status TEXT,
    created_time TEXT,
    updated_time TEXT,
    detection_source TEXT,
    assigned_to TEXT,
    resolution_time TEXT,
    incident_data TEXT
);

CREATE TABLE IF NOT EXISTS playbook_executions (
    execution_id TEXT PRIMARY KEY,
    incident_id TEXT,
    playbook_id TEXT,
    status TEXT,
    start_time TEXT,
    end_time TEXT,
    executed_by TEXT,
    total_tasks INTEGER,
    completed_tasks INTEGER,
    failed_tasks INTEGER,
    execution_data TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    incident_id TEXT,
    evidence_type TEXT,
    source_system TEXT,
    collection_time TEXT,
    collector TEXT,
    file_path TEXT,
    file_size INTEGER,
    file_hash TEXT,
    description TEXT,
    evidence_data TEXT
);

CREATE TABLE IF NOT EXISTS forensic_analysis (
    analysis_id TEXT PRIMARY KEY,
    incident_id TEXT,
    analysis_type TEXT,
    start_time TEXT,
    end_time TEXT,
    analyst TEXT,
    confidence_score REAL,
    analysis_data TEXT
);
