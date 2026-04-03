-- Workflow orchestration engine tables
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    version TEXT NOT NULL,
    definition TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL UNIQUE,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_data TEXT,
    variables TEXT,
    task_states TEXT,
    task_results TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    triggered_by TEXT NOT NULL,
    error_message TEXT,
    metrics TEXT
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id TEXT NOT NULL UNIQUE,
    execution_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    approver TEXT NOT NULL,
    request_data TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    approved_at TEXT,
    approved_by TEXT,
    comments TEXT
);
