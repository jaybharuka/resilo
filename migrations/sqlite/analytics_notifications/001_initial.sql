-- Notification analytics tables
CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    alert_id TEXT,
    title TEXT,
    severity TEXT,
    channel TEXT,
    recipients TEXT,
    sent_at TEXT,
    status TEXT,
    delivery_time_ms INTEGER,
    read_time_ms INTEGER,
    acknowledgment_time_ms INTEGER,
    total_response_time_ms INTEGER,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    notification_id TEXT,
    event_type TEXT,
    channel TEXT,
    timestamp TEXT,
    user_id TEXT,
    response_time_ms INTEGER,
    success BOOLEAN,
    error_message TEXT,
    metadata TEXT,
    FOREIGN KEY (notification_id) REFERENCES notifications (notification_id)
);

CREATE INDEX IF NOT EXISTS idx_notifications_sent_at ON notifications(sent_at);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_channel ON events(channel);
