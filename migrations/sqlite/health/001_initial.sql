-- Daily health reporter tables
CREATE TABLE IF NOT EXISTS health_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cpu REAL NOT NULL,
    memory REAL NOT NULL,
    disk REAL NOT NULL,
    temperature REAL NOT NULL,
    network_in REAL NOT NULL,
    network_out REAL NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON health_metrics(timestamp);
