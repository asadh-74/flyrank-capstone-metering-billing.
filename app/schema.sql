-- Core schema for the metering & billing engine.
-- Money is always stored as integer cents. Never a float column, anywhere.

CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,               -- 'free' | 'pro'
    api_call_limit INTEGER NOT NULL,         -- per month
    ai_token_limit INTEGER NOT NULL,         -- per month
    monthly_price_cents INTEGER NOT NULL,    -- flat subscription price
    stripe_price_id TEXT                     -- Stripe Price ID for Checkout (pro only)
);

CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    stripe_customer_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    stripe_subscription_id TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',   -- active | past_due | canceled | unpaid
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per billable action. The UNIQUE constraint on
-- (tenant_id, idempotency_key) is what makes "retry the same request twice"
-- physically impossible to double-count, even under concurrent retries —
-- the database enforces it, not just application logic.
CREATE TABLE IF NOT EXISTS usage_events (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    idempotency_key TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('api_call', 'ai_tokens')),
    quantity INTEGER NOT NULL DEFAULT 1,      -- used for api_call rollups
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0, -- subset of input_tokens billed cheaper
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0, -- billed at the output rate
    cost_cents INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_created
    ON usage_events (tenant_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_type
    ON usage_events (tenant_id, type, created_at);

-- Every Stripe webhook event id we've successfully processed. A replayed
-- event (same id) is a no-op lookup against this table, not a re-run of
-- side effects.
CREATE TABLE IF NOT EXISTS processed_webhook_events (
    event_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the two plans this capstone's realistic scope calls for.
-- ON CONFLICT so this is safe to run every startup.
INSERT INTO plans (name, api_call_limit, ai_token_limit, monthly_price_cents, stripe_price_id)
VALUES
    ('free', 1000, 100000, 0, NULL),
    ('pro', 50000, 5000000, 2000, NULL)
ON CONFLICT (name) DO NOTHING;
