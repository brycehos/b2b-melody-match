import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import agent
import auth_middleware
import background_indexer
import database
import embeddings as emb
import job_queue
import search as search_module
from models import AgentEvent, SearchRequest, CATALOG_GATED_PLANS, SEARCH_LIMITS
from routes.billing import router as billing_router
from routes.webhooks import router as webhooks_router

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
# Uvicorn sets the root logger to WARNING by default; our modules use INFO.
# Override just the modules we care about so their logs appear in the terminal.
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
for _mod in ("background_indexer", "job_queue"):
    logging.getLogger(_mod).setLevel(logging.INFO)

_log = logging.getLogger(__name__)

# ── Dev mode ────────────────────────────────────────────────────────────────
# When DEV_MODE is enabled, all paid-tier gating is bypassed: no monthly search
# quota, no catalog restriction (full catalog for everyone), and usage counters
# are not incremented. Set DEV_MODE=true in backend/.env for local testing.
DEV_MODE = os.getenv("DEV_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
if DEV_MODE:
    _log.warning(
        "⚙️  DEV_MODE enabled — quota enforcement and catalog gating are BYPASSED "
        "(unlimited queries, full catalog). Do NOT enable in production."
    )

app = FastAPI(title="MelodyMatch API", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    # Pre-populate the in-process known-artists set from Supabase so we never
    # re-index an artist that was fully indexed in a previous server run.
    try:
        artist_keys = await asyncio.get_event_loop().run_in_executor(
            None, background_indexer.load_indexed_artist_keys
        )
        job_queue.seed_known(artist_keys)
    except Exception as exc:
        # Non-fatal — worst case we re-index an artist once; Pinecone upsert is idempotent
        import logging
        logging.getLogger(__name__).warning("Could not pre-seed known artists: %s", exc)

    # Start the background indexing worker (runs for the lifetime of the process)
    asyncio.create_task(background_indexer.run_worker(), name="background-indexer")

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(billing_router)
app.include_router(webhooks_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/admin/indexer")
async def indexer_status():
    """
    Live status of the background artist indexer.

    Returns:
      worker        — which artist is being processed right now (null if idle)
      queue         — artists waiting in the queue
      recent_enqueues — last 50 enqueue events (artist + timestamp + queue depth)
      history       — last 20 artists fully indexed, from Supabase
      totals        — aggregate counts
    """
    loop = asyncio.get_event_loop()

    # Fetch indexing history from Supabase (sync call, run in executor)
    def _fetch_history():
        try:
            db = database.get_client()
            result = (
                db.table("indexed_artists")
                .select("artist_name, songs_indexed, status, indexed_at")
                .order("indexed_at", desc=True)
                .limit(20)
                .execute()
            )
            return result.data or []
        except Exception as exc:
            _log.warning("Could not fetch indexer history from Supabase: %s", exc)
            return []

    def _fetch_totals():
        try:
            db = database.get_client()
            result = db.table("indexed_artists").select("songs_indexed").execute()
            rows = result.data or []
            return {
                "artists_indexed": len(rows),
                "songs_indexed":   sum(r.get("songs_indexed", 0) for r in rows),
            }
        except Exception:
            return {"artists_indexed": 0, "songs_indexed": 0}

    history, totals = await asyncio.gather(
        loop.run_in_executor(None, _fetch_history),
        loop.run_in_executor(None, _fetch_totals),
    )

    queue_status  = job_queue.get_status()
    worker_state  = background_indexer.get_worker_state()

    return {
        "worker":         worker_state,
        "queue":          queue_status,
        "history":        history,
        "totals":         totals,
    }


@app.post("/api/search")
async def search(req: SearchRequest, request: Request):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # ── Resolve authenticated user (optional) ────────────────────────────────
    auth_header = request.headers.get("Authorization", "")
    clerk_user_id = auth_middleware.get_clerk_user_id(auth_header)

    user = None
    plan = "anonymous"

    if clerk_user_id:
        user = await asyncio.get_event_loop().run_in_executor(
            None, database.get_or_create_user, clerk_user_id
        )
        # Reset monthly counter if the billing window has rolled over
        user = await asyncio.get_event_loop().run_in_executor(
            None, database.maybe_reset_monthly_count, user
        )
        plan = user.get("plan", "free")

        # ── Quota enforcement (skipped in dev mode) ──────────────────────────
        if not DEV_MODE:
            limit = SEARCH_LIMITS.get(plan, 10)
            used = user.get("searches_used_this_month", 0)
            if used >= limit:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": "Monthly search limit reached",
                        "plan": plan,
                        "limit": limit,
                        "used": used,
                    },
                )

    # ── Catalog gating (disabled in dev mode) ────────────────────────────────
    restrict_to_popular = (plan in CATALOG_GATED_PLANS) and not DEV_MODE

    # ── Increment usage counter (fire-and-forget; skipped in dev mode) ───────
    if user and not DEV_MODE:
        asyncio.get_event_loop().run_in_executor(
            None, database.increment_search_count, user["id"]
        )

    return StreamingResponse(
        agent.run_streaming(req.query, req.search_type, restrict_to_popular=restrict_to_popular),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Audio upload / Shazam-like matching ──────────────────────────────────────

_MAX_AUDIO_BYTES = 10 * 1024 * 1024   # 10 MB hard cap


@app.post("/api/audio-search")
async def audio_search(request: Request, file: UploadFile = File(...)):
    """
    Accept a short audio clip, extract its sonic fingerprint via librosa,
    embed the resulting description with Voyage AI, and query Pinecone for the
    closest matching songs in the audio namespace.

    Returns a JSON list of SongResult-like dicts (same shape as /api/search
    results) so the frontend can reuse its existing ResultCard component.
    """
    # ── Auth (optional) ───────────────────────────────────────────────────────
    auth_header = request.headers.get("Authorization", "")
    clerk_user_id = auth_middleware.get_clerk_user_id(auth_header)
    plan = "anonymous"

    if clerk_user_id:
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(
            None, database.get_or_create_user, clerk_user_id
        )
        user = await loop.run_in_executor(
            None, database.maybe_reset_monthly_count, user
        )
        plan = user.get("plan", "free")

        if not DEV_MODE:
            limit = SEARCH_LIMITS.get(plan, 10)
            used = user.get("searches_used_this_month", 0)
            if used >= limit:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "message": "Monthly search limit reached",
                        "plan": plan,
                        "limit": limit,
                        "used": used,
                    },
                )
            loop.run_in_executor(None, database.increment_search_count, user["id"])

    restrict_to_popular = (plan in CATALOG_GATED_PLANS) and not DEV_MODE

    # ── Read + validate audio bytes ───────────────────────────────────────────
    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 10 MB)")
    if len(audio_bytes) < 1024:
        raise HTTPException(status_code=400, detail="Audio file too small or empty")

    # ── Feature extraction ────────────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    try:
        import audio_analyzer
        features = await loop.run_in_executor(
            None, audio_analyzer.analyze_audio, audio_bytes
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Audio analysis failed: {exc}",
        )

    # ── Build text description and embed ─────────────────────────────────────
    description = emb.generate_audio_description(
        features=features,
        track_name="uploaded audio",
        artist="",
        genre="",
    )

    try:
        query_vec = await loop.run_in_executor(
            None, emb.embed_query, description
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")

    # ── Search Pinecone ───────────────────────────────────────────────────────
    pinecone_filter = {"catalog_tier": {"$eq": "popular"}} if restrict_to_popular else None
    try:
        songs = await loop.run_in_executor(
            None,
            lambda: search_module.search_by_audio_mood(
                query=description,
                top_k=10,
                restrict_to_popular=restrict_to_popular,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")

    # ── Serialise ─────────────────────────────────────────────────────────────
    def _ser(s):
        return {
            "song_id":      s.song_id,
            "title":        s.title,
            "artist":       s.artist,
            "album":        s.album,
            "year":         s.year,
            "genre":        s.genre,
            "duration":     s.duration,
            "similarity":   s.similarity,
            "preview_url":  s.preview_url,
            "image_url":    s.image_url,
            "spotify_url":  s.spotify_url,
            "match_reason": "Matched by sonic fingerprint: similar tempo, energy, and timbral qualities to your uploaded audio.",
        }

    return {
        "songs":       [_ser(s) for s in songs[:8]],
        "explanation": f"Songs matched by audio fingerprint. Detected: {description}",
        "features":    features,
    }
