-- Configuration management system tables
CREATE TABLE IF NOT EXISTS configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id TEXT NOT NULL UNIQUE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    config_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    source TEXT NOT NULL,
    encrypted BOOLEAN DEFAULT 0,
    sensitive BOOLEAN DEFAULT 0,
    description TEXT,
    tags TEXT,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    checksum TEXT
);

CREATE TABLE IF NOT EXISTS configuration_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id TEXT NOT NULL,
    config_id TEXT NOT NULL,
    key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    environment TEXT NOT NULL,
    change_type TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    change_reason TEXT,
    timestamp TEXT NOT NULL,
    rollback_data TEXT
);

CREATE TABLE IF NOT EXISTS configuration_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    target_environment TEXT NOT NULL,
    template_data TEXT NOT NULL,
    variables TEXT,
    created_at TEXT NOT NULL
);
