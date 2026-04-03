-- Enterprise API gateway tables
CREATE TABLE IF NOT EXISTS api_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    user_id TEXT,
    api_key TEXT,
    ip_address TEXT NOT NULL,
    status_code INTEGER,
    processing_time REAL,
    response_size INTEGER,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT
);
