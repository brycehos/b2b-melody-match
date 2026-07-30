# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (React/Vite)
```bash
npm install          # install dependencies
npm run dev          # dev server on http://localhost:3000
npm run build        # production build → build/
```

### Backend (FastAPI/Python)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000   # dev server on http://localhost:8000
```

The frontend reads `VITE_API_URL` (defaults to `http://localhost:8000`); both servers must run simultaneously for local development.

## Architecture

This is a full-stack AI music discovery app ("MelodyMatch"). Users describe music by mood, melody, lyrics, or by uploading an audio clip, and the app returns semantically similar songs.

### Request flow (text search)
1. React frontend (`src/api/client.ts`) POSTs to `/api/search` with `{query, search_type}`
2. FastAPI (`backend/main.py`) enforces auth (Clerk JWT) and quota, then calls `agent.run_streaming()`
3. `backend/agent.py` runs a Claude `claude-sonnet-4-6` agentic loop with tool use over SSE. Tools: `search_by_artist`, `search_by_audio_mood`, `search_by_lyrics_theme`, `search_combined`, `queue_artist_index`, `return_results`
4. Each tool call hits `backend/search.py`, which embeds the query via Voyage AI (`voyage-3` model) and queries Pinecone
5. Results stream back as `AgentEvent` SSE events; `useSearch` hook in the frontend accumulates them and updates state

### Request flow (audio search)
1. User records/uploads audio via `AudioUpload` component
2. Browser converts to WAV and POSTs to `/api/audio-search` with the file
3. Backend uses `librosa` (via `audio_analyzer.py`) to extract sonic features (energy, tempo, valence, etc.)
4. Features are converted to a text description (`embeddings.generate_audio_description`), embedded, and queried against Pinecone's `audio` namespace directly (no Claude agent)
5. Returns JSON (not SSE)

### Background indexing
When a search mentions an artist, the agent calls `queue_artist_index`. `job_queue.py` manages an asyncio queue; `background_indexer.py` runs a single long-lived coroutine (`run_worker`) started at app startup that processes one artist at a time. Pipeline: iTunes Search API → Voyage AI embeddings → Pinecone upsert → Supabase record. Admin status visible at `GET /api/admin/indexer`.

### Data storage
- **Pinecone**: two namespaces — `audio` (sonic feature vectors) and `lyrics` (lyrical theme vectors). Vectors store all song metadata as flat fields (`song_id`, `title`, `artist`, `artist_lower`, `af_*` audio features, `catalog_tier`).
- **Supabase**: users table (Clerk ID, plan, monthly search count), subscriptions table (Stripe), indexed_artists table (prevents re-indexing).

### Auth & billing
- **Clerk** handles frontend auth (`@clerk/clerk-react`). JWT tokens are passed as `Authorization: Bearer <token>` headers.
- `backend/auth_middleware.py` verifies JWTs via Clerk's JWKS endpoint.
- **Stripe** handles subscriptions. Webhooks (`backend/routes/webhooks.py`) update the user's plan in Supabase. Billing portal managed in `backend/routes/billing.py`.
- Plans: `anonymous` (3 searches, popular catalog only), `free` (10/month, popular catalog only), `explorer` (75/month, full catalog), `unlimited` (300/month, full catalog). Plan constants live in `backend/models.py` (`SEARCH_LIMITS`, `CATALOG_GATED_PLANS`).

### Frontend structure
- `src/App.tsx` — single-page app, owns all top-level state
- `src/hooks/useSearch.ts` — SSE streaming state machine
- `src/hooks/useAuth.ts` — anonymous localStorage counter + Clerk auth + backend quota fetch
- `src/hooks/useBilling.ts` — Stripe billing portal redirect
- `src/api/client.ts` — `streamSearch` (SSE) and `audioSearch` (multipart)
- `src/themes/index.ts` — theme objects (spotify, light, dark, ocean); passed as props throughout, no CSS-in-JS library
- `src/components/ui/` — shadcn/ui components (Radix UI primitives + Tailwind)
- Custom components use inline styles with theme tokens, not Tailwind

## Environment variables

Copy `backend/.env.example` to `backend/.env`. Required keys:
- `ANTHROPIC_API_KEY` — Claude API
- `VOYAGE_API_KEY` — Voyage AI embeddings (free tier: 3 RPM — add payment method to unlock full rate)
- `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` (default: `melodymatch`)
- `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `CLERK_WEBHOOK_SECRET`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_EXPLORER_PRICE_ID`, `STRIPE_UNLIMITED_PRICE_ID`
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (use service_role key, bare project URL without `/rest/v1/`)
- `FRONTEND_URL` (default: `http://localhost:3000`)

Frontend env: `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` (set in `.env` at repo root).

## Key implementation details

- The agent loop in `agent.py` uses `AsyncAnthropic` (not the sync client) — sync client blocks the event loop inside an async generator, causing Uvicorn to drop SSE connections mid-stream.
- All sync I/O (Voyage AI, Pinecone, Supabase, iTunes) runs inside `loop.run_in_executor(None, ...)` to avoid blocking the event loop.
- Pinecone cosine similarity scores are remapped from the `0.40–0.65` meaningful range to `0–1` via `_SCORE_CEILING = 0.65` in `search.py`.
- `search_by_artist` uses Pinecone metadata filtering with a `$or` on `artist_lower` (newer vectors) and `artist` (older vectors with case variations) to handle case-insensitive lookups.
- Audio features in Pinecone metadata are stored as flat `af_*` prefixed keys because Pinecone doesn't support nested dict metadata.
- The `catalog_tier` metadata field (`"popular"` vs `"full"`) gates free/anonymous users to a restricted song set via Pinecone filter.
