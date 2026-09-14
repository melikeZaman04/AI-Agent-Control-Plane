CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    fidelity_level TEXT NOT NULL, -- NATIVE, SESSION_LOG, PASSIVE
    task_description TEXT NOT NULL,
    status TEXT NOT NULL,         -- RUNNING, SUCCESS, FAILED
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    context_tokens INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,     -- FILE_READ, FILE_WRITE, TOOL_CALL, ERROR
    target TEXT,                  -- İlgili dosya veya tool adı
    payload TEXT,                 -- JSON veya detaylı metin verisi
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS provider_sessions (
    provider TEXT NOT NULL,
    provider_session_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    PRIMARY KEY (provider, provider_session_id)
);
