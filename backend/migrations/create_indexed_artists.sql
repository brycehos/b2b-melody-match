-- Migration: background artist indexing tracker
-- Run in Supabase SQL Editor: https://app.supabase.com → your project → SQL Editor

CREATE TABLE IF NOT EXISTS indexed_artists (
    id           BIGSERIAL PRIMARY KEY,
    artist_name  TEXT        NOT NULL,
    artist_key   TEXT        NOT NULL UNIQUE,   -- lowercase normalised, used for dedup
    songs_indexed INTEGER    NOT NULL DEFAULT 0,
    status       TEXT        NOT NULL DEFAULT 'completed',
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookup by key (used on every enqueue check at startup)
CREATE INDEX IF NOT EXISTS indexed_artists_key_idx ON indexed_artists (artist_key);

-- Optional: allow the service role key used by the backend full access
-- (Supabase service role already bypasses RLS, so no policy needed)
