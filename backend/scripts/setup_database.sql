-- MelodyMatch database schema
-- Run this in the Supabase SQL Editor: https://supabase.com/dashboard → your project → SQL Editor

-- Users table (populated via Clerk webhook on user creation)
CREATE TABLE IF NOT EXISTS users (
    id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id             TEXT        UNIQUE NOT NULL,
    email                     TEXT,
    stripe_customer_id        TEXT        UNIQUE,
    plan                      TEXT        NOT NULL DEFAULT 'free'
                                          CHECK (plan IN ('free', 'explorer', 'unlimited')),
    searches_used_this_month  INTEGER     NOT NULL DEFAULT 0,
    searches_reset_at         TIMESTAMPTZ NOT NULL DEFAULT (date_trunc('month', NOW()) + INTERVAL '1 month'),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Subscriptions table (populated/updated via Stripe webhooks)
CREATE TABLE IF NOT EXISTS subscriptions (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stripe_subscription_id   TEXT        UNIQUE NOT NULL,
    stripe_price_id          TEXT        NOT NULL,
    plan                     TEXT        NOT NULL CHECK (plan IN ('explorer', 'unlimited')),
    status                   TEXT        NOT NULL,  -- active, canceled, past_due, trialing
    current_period_end       TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS subscriptions_updated_at ON subscriptions;
CREATE TRIGGER subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Atomic increment for search count (avoids race conditions)
CREATE OR REPLACE FUNCTION increment_search_count(user_id_input UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE users
    SET searches_used_this_month = searches_used_this_month + 1
    WHERE id = user_id_input;
END;
$$ LANGUAGE plpgsql;

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_users_clerk_user_id    ON users (clerk_user_id);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer   ON users (stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subs_stripe_sub_id      ON subscriptions (stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subs_user_id            ON subscriptions (user_id);
