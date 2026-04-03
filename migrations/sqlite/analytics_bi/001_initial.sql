-- Business intelligence engine tables
CREATE TABLE IF NOT EXISTS kpi_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    current_value REAL NOT NULL,
    target_value REAL NOT NULL,
    previous_value REAL NOT NULL,
    unit TEXT NOT NULL,
    trend TEXT NOT NULL,
    confidence REAL NOT NULL,
    last_updated TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS roi_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    initiative TEXT NOT NULL,
    investment_amount REAL NOT NULL,
    savings_achieved REAL NOT NULL,
    roi_percentage REAL NOT NULL,
    payback_period_months REAL NOT NULL,
    net_present_value REAL NOT NULL,
    confidence_score REAL NOT NULL,
    risk_factors TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategic_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    impact_score REAL NOT NULL,
    description TEXT NOT NULL,
    recommendations TEXT,
    data_sources TEXT,
    confidence REAL NOT NULL,
    generated_at TEXT NOT NULL
);
