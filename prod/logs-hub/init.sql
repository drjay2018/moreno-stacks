CREATE TABLE logs (
    id SERIAL PRIMARY KEY,
    app_name TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    resolved BOOLEAN DEFAULT FALSE,
    resolution TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE telegram_pending (
    telegram_message_id BIGINT PRIMARY KEY,
    log_id INTEGER REFERENCES logs(id)
);
