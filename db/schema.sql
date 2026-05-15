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

-- Migration: price targets and alert types
-- Run this block separately if the tables above already exist

CREATE TABLE IF NOT EXISTS price_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL UNIQUE,
    stop_loss FLOAT NOT NULL,
    target1 FLOAT NOT NULL,
    target2 FLOAT NOT NULL,
    stop_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    target1_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    target2_triggered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type TEXT NOT NULL DEFAULT 'signal';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS message TEXT;

-- Migration: momentum scan results
-- Run this block separately if the tables above already exist

CREATE TABLE IF NOT EXISTS momentum_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL,
    current_price FLOAT,
    volume_surge FLOAT,
    price_change_5d FLOAT,
    price_change_20d FLOAT,
    pct_from_high FLOAT,
    momentum_score FLOAT,
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_momentum_scanned_at ON momentum_results(scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_momentum_ticker ON momentum_results(ticker);

-- Migration: automated trading log
-- Run this block separately if the tables above already exist

CREATE TABLE IF NOT EXISTS auto_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    score FLOAT,
    signal TEXT,
    order_type TEXT,
    qty FLOAT,
    limit_price FLOAT,
    stop_price FLOAT,
    order_id TEXT,
    status TEXT NOT NULL,
    error TEXT,
    traded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auto_trades_traded_at ON auto_trades(traded_at DESC);
CREATE INDEX IF NOT EXISTS idx_auto_trades_ticker ON auto_trades(ticker);

-- Migration: Claude autonomous trader log
-- Run this block separately if the tables above already exist

CREATE TABLE IF NOT EXISTS claude_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    qty FLOAT,
    limit_price FLOAT,
    stop_price FLOAT,
    allocation_pct FLOAT,
    reasoning TEXT,
    status TEXT NOT NULL,
    error TEXT,
    traded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claude_trades_traded_at ON claude_trades(traded_at DESC);
CREATE INDEX IF NOT EXISTS idx_claude_trades_ticker ON claude_trades(ticker);
