"""
Background artist indexer.

run_worker() is a long-running coroutine started once at app startup via
asyncio.create_task().  It pulls artist names from the job queue one at a
time and indexes their top tracks into Pinecone without ever blocking the
FastAPI event loop — all sync I/O (iTunes, Voyage AI, Pinecone, Supabase)
runs inside loop.run_in_executor(None, ...).

Pipeline per artist
───────────────────
1. Check Supabase — skip if already fully indexed
2. Fetch top TRACKS_PER_ARTIST songs from iTunes Search API
3. Cross-check against Pinecone to skip already-indexed track IDs
4. Derive genre from iTunes primaryGenreName → genre-default audio features
5. Embed audio descriptions with Voyage AI
6. Upsert audio vectors to Pinecone
7. Record completion in Supabase indexed_artists table
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

import database
import embeddings as emb
import itunes_client as itunes
import job_queue
import pinecone_client as pc

logger = logging.getLogger(__name__)

TRACKS_PER_ARTIST  = 30
BATCH_EMBED_SIZE   = 32
UPSERT_BATCH_SIZE  = 50

# ── Genre feature defaults (same values as seed_songs.py) ────────────────────

_GENRE_DEFAULTS: dict[str, dict] = {
    "pop":        {"energy": 0.65, "valence": 0.60, "tempo": 120.0, "danceability": 0.70,
                   "acousticness": 0.20, "instrumentalness": 0.04, "speechiness": 0.07,
                   "loudness": -6.0,  "key": 5, "mode": 1, "liveness": 0.14},
    "rock":       {"energy": 0.80, "valence": 0.50, "tempo": 135.0, "danceability": 0.55,
                   "acousticness": 0.10, "instrumentalness": 0.10, "speechiness": 0.05,
                   "loudness": -5.0,  "key": 7, "mode": 1, "liveness": 0.20},
    "hip-hop":    {"energy": 0.70, "valence": 0.55, "tempo": 95.0,  "danceability": 0.80,
                   "acousticness": 0.10, "instrumentalness": 0.04, "speechiness": 0.25,
                   "loudness": -6.0,  "key": 8, "mode": 0, "liveness": 0.12},
    "r&b":        {"energy": 0.60, "valence": 0.55, "tempo": 95.0,  "danceability": 0.75,
                   "acousticness": 0.25, "instrumentalness": 0.04, "speechiness": 0.12,
                   "loudness": -7.0,  "key": 5, "mode": 0, "liveness": 0.12},
    "country":    {"energy": 0.65, "valence": 0.65, "tempo": 115.0, "danceability": 0.60,
                   "acousticness": 0.50, "instrumentalness": 0.04, "speechiness": 0.04,
                   "loudness": -7.0,  "key": 2, "mode": 1, "liveness": 0.15},
    "electronic": {"energy": 0.85, "valence": 0.65, "tempo": 128.0, "danceability": 0.85,
                   "acousticness": 0.05, "instrumentalness": 0.60, "speechiness": 0.05,
                   "loudness": -5.0,  "key": 9, "mode": 0, "liveness": 0.10},
    "jazz":       {"energy": 0.45, "valence": 0.55, "tempo": 120.0, "danceability": 0.55,
                   "acousticness": 0.80, "instrumentalness": 0.70, "speechiness": 0.05,
                   "loudness": -12.0, "key": 6, "mode": 0, "liveness": 0.25},
    "classical":  {"energy": 0.30, "valence": 0.45, "tempo": 100.0, "danceability": 0.30,
                   "acousticness": 0.95, "instrumentalness": 0.95, "speechiness": 0.04,
                   "loudness": -18.0, "key": 0, "mode": 1, "liveness": 0.10},
    "metal":      {"energy": 0.90, "valence": 0.40, "tempo": 150.0, "danceability": 0.45,
                   "acousticness": 0.05, "instrumentalness": 0.15, "speechiness": 0.06,
                   "loudness": -4.0,  "key": 7, "mode": 0, "liveness": 0.22},
    "folk":       {"energy": 0.40, "valence": 0.55, "tempo": 100.0, "danceability": 0.45,
                   "acousticness": 0.85, "instrumentalness": 0.10, "speechiness": 0.04,
                   "loudness": -12.0, "key": 2, "mode": 1, "liveness": 0.15},
    "latin":      {"energy": 0.75, "valence": 0.75, "tempo": 110.0, "danceability": 0.82,
                   "acousticness": 0.20, "instrumentalness": 0.04, "speechiness": 0.12,
                   "loudness": -6.0,  "key": 5, "mode": 0, "liveness": 0.18},
    "blues":      {"energy": 0.55, "valence": 0.45, "tempo": 100.0, "danceability": 0.55,
                   "acousticness": 0.55, "instrumentalness": 0.20, "speechiness": 0.05,
                   "loudness": -10.0, "key": 7, "mode": 0, "liveness": 0.30},
    "reggae":     {"energy": 0.50, "valence": 0.65, "tempo": 80.0,  "danceability": 0.70,
                   "acousticness": 0.35, "instrumentalness": 0.08, "speechiness": 0.12,
                   "loudness": -9.0,  "key": 9, "mode": 0, "liveness": 0.20},
    "indie":      {"energy": 0.55, "valence": 0.50, "tempo": 120.0, "danceability": 0.55,
                   "acousticness": 0.40, "instrumentalness": 0.15, "speechiness": 0.05,
                   "loudness": -9.0,  "key": 5, "mode": 1, "liveness": 0.15},
}

# iTunes primaryGenreName → our feature key
_ITUNES_GENRE_MAP: dict[str, str] = {
    "pop": "pop", "pop music": "pop", "dance pop": "pop",
    "rock": "rock", "alternative": "rock", "alternative & punk": "rock",
    "punk": "rock", "grunge": "rock", "hard rock": "rock",
    "hip-hop/rap": "hip-hop", "hip-hop": "hip-hop", "rap": "hip-hop",
    "r&b/soul": "r&b", "soul": "r&b", "rhythm & blues": "r&b", "neo soul": "r&b",
    "country": "country", "country & folk": "country",
    "dance": "electronic", "electronic": "electronic", "house": "electronic",
    "techno": "electronic", "edm": "electronic", "trance": "electronic",
    "ambient": "electronic", "electronica": "electronic",
    "jazz": "jazz", "jazz & blues": "jazz",
    "classical": "classical", "opera": "classical", "chamber music": "classical",
    "metal": "metal", "heavy metal": "metal",
    "folk": "folk", "folk & singer/songwriter": "folk", "singer/songwriter": "folk",
    "latin": "latin", "reggaeton": "latin", "salsa y tropical": "latin",
    "blues": "blues",
    "reggae": "reggae", "ska": "reggae",
    "indie pop": "indie", "indie rock": "indie", "indie": "indie",
    "alternative pop": "indie", "dream pop": "indie",
}


def _resolve_genre(itunes_genre: str) -> str:
    return _ITUNES_GENRE_MAP.get(itunes_genre.strip().lower(), "pop")


def _jitter(features: dict) -> dict:
    """Add small random variation so tracks from the same artist aren't identical."""
    return {
        k: round(v + random.uniform(-0.06, 0.06), 4) if isinstance(v, float) else v
        for k, v in features.items()
    }


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _is_indexed(artist_key: str) -> bool:
    try:
        db = database.get_client()
        result = (
            db.table("indexed_artists")
            .select("id")
            .eq("artist_key", artist_key)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


def _record_indexed(artist_name: str, artist_key: str, songs_count: int) -> None:
    try:
        db = database.get_client()
        db.table("indexed_artists").upsert(
            {
                "artist_name":   artist_name,
                "artist_key":    artist_key,
                "songs_indexed": songs_count,
                "status":        "completed",
            },
            on_conflict="artist_key",
        ).execute()
    except Exception as e:
        logger.warning("[indexer] Could not record artist in Supabase: %s", e)


def load_indexed_artist_keys() -> list[str]:
    """
    Return all artist_key values from Supabase indexed_artists.
    Called once at startup to pre-populate job_queue._known.
    """
    try:
        db = database.get_client()
        result = db.table("indexed_artists").select("artist_key").execute()
        return [row["artist_key"] for row in (result.data or [])]
    except Exception as e:
        logger.warning("[indexer] Could not load indexed artists from Supabase: %s", e)
        return []


# ── Core sync indexing pipeline ───────────────────────────────────────────────

def _index_artist_sync(artist_name: str) -> int:
    """
    Full indexing pipeline for one artist.  Synchronous — run in a thread
    executor so it never blocks the event loop.

    Returns the number of new songs indexed.
    """
    artist_key = artist_name.strip().lower()
    logger.info("[indexer] Processing: %s", artist_name)

    # Re-check Supabase (handles race if the same artist was enqueued twice
    # before the first job completed, e.g. across a restart)
    if _is_indexed(artist_key):
        logger.info("[indexer] Already indexed: %s — skipping", artist_name)
        return 0

    # ── 1. Fetch tracks from iTunes ───────────────────────────────────────────
    try:
        raw_tracks = itunes.search_tracks_by_artist(artist_name, limit=TRACKS_PER_ARTIST)
    except Exception as e:
        logger.warning("[indexer] iTunes fetch failed for %s: %s", artist_name, e)
        return 0

    if not raw_tracks:
        logger.info("[indexer] No iTunes results for: %s", artist_name)
        _record_indexed(artist_name, artist_key, 0)
        return 0

    # ── 2. Skip tracks already in Pinecone ────────────────────────────────────
    track_ids = [str(t["trackId"]) for t in raw_tracks if t.get("trackId")]
    if not track_ids:
        return 0

    index = pc.get_index()
    fetch_result = index.fetch(
        ids=[f"{tid}_audio" for tid in track_ids],
        namespace=pc.NAMESPACE_AUDIO,
    )
    existing_vecs = getattr(fetch_result, "vectors", None) or {}
    already_indexed = {vid.replace("_audio", "") for vid in existing_vecs}
    new_tracks = [t for t in raw_tracks if str(t.get("trackId", "")) not in already_indexed]

    if not new_tracks:
        logger.info("[indexer] All tracks already in Pinecone for: %s", artist_name)
        _record_indexed(artist_name, artist_key, 0)
        return 0

    logger.info("[indexer] %s — %d new tracks to index", artist_name, len(new_tracks))

    # ── 3. Build song entries ─────────────────────────────────────────────────
    song_entries = []
    for track in new_tracks:
        genre_raw = track.get("primaryGenreName", "pop")
        genre     = _resolve_genre(genre_raw)
        features  = _jitter(_GENRE_DEFAULTS.get(genre, _GENRE_DEFAULTS["pop"]))
        song_entries.append({
            "song_id":        str(track["trackId"]),
            "title":          track.get("trackName", ""),
            "artist":         track.get("artistName", ""),
            "album":          track.get("collectionName", ""),
            "year":           int((track.get("releaseDate") or "0000")[:4]),
            "genre":          genre,
            "duration":       itunes.format_duration(track.get("trackTimeMillis", 0)),
            "preview_url":    track.get("previewUrl") or "",
            "image_url":      itunes.high_res_artwork(track.get("artworkUrl100")) or "",
            "spotify_url":    itunes.external_url(
                                  track.get("artistName", ""),
                                  track.get("trackName", ""),
                              ),
            "catalog_tier":   "full",   # background-indexed artists unlock for paid plans
            "audio_features": features,
        })

    # ── 4. Embed audio descriptions ───────────────────────────────────────────
    descriptions = [
        emb.generate_audio_description(
            sd["audio_features"], sd["title"], sd["artist"], sd["genre"]
        )
        for sd in song_entries
    ]
    audio_embeddings: list[list[float]] = []
    for i in range(0, len(descriptions), BATCH_EMBED_SIZE):
        batch = descriptions[i : i + BATCH_EMBED_SIZE]
        audio_embeddings.extend(emb.embed_texts(batch))
        time.sleep(0.1)

    # ── 5. Upsert to Pinecone ─────────────────────────────────────────────────
    vectors = []
    for sd, emb_vec in zip(song_entries, audio_embeddings):
        meta = {
            k: (v if v is not None else "")
            for k, v in sd.items()
            if k != "audio_features"
        }
        # artist_lower enables case-insensitive metadata filtering in search_by_artist
        meta["artist_lower"] = sd.get("artist", "").strip().lower()
        af = sd["audio_features"]
        meta.update({
            "af_energy":           float(af.get("energy", 0)),
            "af_tempo":            float(af.get("tempo", 0)),
            "af_valence":          float(af.get("valence", 0)),
            "af_danceability":     float(af.get("danceability", 0)),
            "af_acousticness":     float(af.get("acousticness", 0)),
            "af_instrumentalness": float(af.get("instrumentalness", 0)),
            "af_speechiness":      float(af.get("speechiness", 0)),
            "af_loudness":         float(af.get("loudness", 0)),
            "af_key":              int(af.get("key", 0)),
            "af_mode":             int(af.get("mode", 0)),
            "af_liveness":         float(af.get("liveness", 0)),
            "namespace":           "audio",
        })
        vectors.append({
            "id":       f"{sd['song_id']}_audio",
            "values":   emb_vec,
            "metadata": meta,
        })

    for i in range(0, len(vectors), UPSERT_BATCH_SIZE):
        pc.upsert_vectors(vectors[i : i + UPSERT_BATCH_SIZE], pc.NAMESPACE_AUDIO)
        time.sleep(0.3)

    # ── 6. Lyrics (best-effort — never fails the audio indexing) ─────────────
    lyrics_count = _index_lyrics_sync(song_entries, vectors)

    # ── 7. Record in Supabase ─────────────────────────────────────────────────
    _record_indexed(artist_name, artist_key, len(song_entries))
    logger.info(
        "[indexer] ✓ Completed %s — %d songs (%d with lyrics)",
        artist_name, len(song_entries), lyrics_count,
    )
    return len(song_entries)


def _index_lyrics_sync(song_entries: list[dict], audio_vectors: list[dict]) -> int:
    """
    Fetch lyrics from Genius for each new track, embed, and upsert to the
    lyrics namespace.  Best-effort: any failure (missing token, rate limit,
    song not on Genius) skips that song without affecting audio indexing.
    """
    try:
        import genius_client as gc
        gc.validate_token()
    except Exception as e:
        logger.info("[indexer] Skipping lyrics (Genius unavailable: %s)", e)
        return 0

    # Audio metadata is reused for the lyrics vector — same song, same fields
    meta_by_song = {v["metadata"]["song_id"]: v["metadata"] for v in audio_vectors}

    texts: list[str] = []
    entries: list[dict] = []
    for sd in song_entries:
        try:
            lyrics = gc.get_lyrics(sd["title"], sd["artist"])
        except Exception:
            lyrics = None
        time.sleep(1.2)   # Genius free-tier pacing
        if lyrics and len(lyrics) > 100:
            meta = dict(meta_by_song.get(sd["song_id"], {}))
            meta["namespace"] = "lyrics"
            texts.append(lyrics[:3000])
            entries.append({"id": f"{sd['song_id']}_lyrics", "metadata": meta})

    if not texts:
        return 0

    lyric_vectors: list[dict] = []
    for i in range(0, len(texts), BATCH_EMBED_SIZE):
        embs = emb.embed_texts(texts[i : i + BATCH_EMBED_SIZE])
        for j, vec in enumerate(embs):
            entry = entries[i + j]
            lyric_vectors.append({
                "id": entry["id"], "values": vec, "metadata": entry["metadata"],
            })

    for i in range(0, len(lyric_vectors), UPSERT_BATCH_SIZE):
        pc.upsert_vectors(lyric_vectors[i : i + UPSERT_BATCH_SIZE], pc.NAMESPACE_LYRICS)
        time.sleep(0.3)

    return len(lyric_vectors)


# ── Async worker coroutine ────────────────────────────────────────────────────

# Tracks the artist currently being processed (None when idle)
_current_artist: str | None = None
_current_started_at: str | None = None


def get_worker_state() -> dict:
    """Return live worker state for the admin status endpoint."""
    return {
        "current_artist":    _current_artist,
        "current_started_at": _current_started_at,
    }


async def run_worker() -> None:
    """
    Long-running coroutine — started once via asyncio.create_task() in main.py.

    Waits for artist names from job_queue, processes them sequentially (one at
    a time), and never blocks the FastAPI event loop.
    """
    global _current_artist, _current_started_at

    loop  = asyncio.get_event_loop()
    queue = job_queue.get_queue()
    logger.info("[indexer] Background worker ready — waiting for jobs")

    while True:
        artist_name = await queue.get()
        job_queue.mark_dequeued(artist_name)

        _current_artist    = artist_name
        _current_started_at = datetime.now(timezone.utc).isoformat()
        logger.info("[indexer] ▶ Starting '%s'", artist_name)

        try:
            n = await loop.run_in_executor(None, _index_artist_sync, artist_name)
            if n > 0:
                logger.info(
                    "[indexer] ✓ Done '%s' — %d new songs added to Pinecone",
                    artist_name, n,
                )
            else:
                logger.info(
                    "[indexer] ✓ Done '%s' — already up to date (0 new songs)",
                    artist_name,
                )
        except Exception as exc:
            logger.error(
                "[indexer] ✗ Failed '%s': %s",
                artist_name, exc, exc_info=True,
            )
        finally:
            _current_artist    = None
            _current_started_at = None
            queue.task_done()
