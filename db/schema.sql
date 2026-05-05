-- Run this entire file once in the Supabase SQL Editor
-- (Supabase dashboard → SQL Editor → New query → paste → Run)

CREATE TABLE IF NOT EXISTS scan_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score FLOAT NOT NULL,
    signal TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    indicator_detail JSONB NOT NULL DEFAULT '{}',
    earnings_warning BOOLEAN NOT NULL DEFAULT FALSE,
    sentiment_flag BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_scan_results_ticker ON scan_results(ticker);
CREATE INDEX IF NOT EXISTS idx_scan_results_scanned_at ON scan_results(scanned_at DESC);

CREATE TABLE IF NOT EXISTS watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL UNIQUE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    previous_signal TEXT NOT NULL,
    new_signal TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('thresholds', '{"BUY": 75, "WATCH CAREFULLY": 55, "HOLD": 35, "REDUCE": 25, "EXIT": 0}'),
    ('group_weights', '{"trend": 0.30, "momentum": 0.25, "volume": 0.20, "volatility": 0.15, "candlesticks": 0.10}'),
    ('indicator_toggles', '{}')
ON CONFLICT (key) DO NOTHING;
