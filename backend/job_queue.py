"""
Shared asyncio job queue for background artist indexing.

Imported by main.py (to start the worker + pre-populate known set) and by
agent.py (to enqueue without blocking the SSE stream).

Design notes
────────────
• The queue is a module-level singleton.  asyncio.Queue() is safe to create
  at import time in Python 3.10+ without a running event loop.
• _known tracks every artist already queued OR already indexed this process
  lifetime so we never enqueue the same artist twice.  It is pre-populated
  from Supabase at startup so it survives server restarts.
• enqueue() is synchronous and non-blocking (put_nowait) — safe to call
  inside an async generator (the SSE handler) without yielding.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 20

# Created at module import — safe in Python 3.10+
_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)

# Lowercase-normalised set of artists already handled (queued or indexed)
_known: set[str] = set()

# Human-readable list of artists currently waiting in the queue (mirrors _queue)
_pending: list[str] = []

# Rolling log of the last 50 enqueue events for the status endpoint
_enqueue_log: deque[dict] = deque(maxlen=50)


def _key(artist: str) -> str:
    return artist.strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Called once at startup ────────────────────────────────────────────────────

def seed_known(artist_keys: list[str]) -> None:
    """Pre-populate _known from Supabase so we skip already-indexed artists."""
    _known.update(artist_keys)
    logger.info("[queue] Pre-seeded %d known artists from Supabase", len(artist_keys))


# ── Called from background_indexer when it picks up a job ────────────────────

def mark_dequeued(artist_name: str) -> None:
    """Remove artist from the pending list when the worker starts processing it."""
    try:
        _pending.remove(artist_name)
    except ValueError:
        pass


# ── Called from agent tool handler ───────────────────────────────────────────

def enqueue(artist_name: str) -> bool:
    """
    Add an artist to the background index queue.
    Returns True if enqueued, False if already known or queue full.
    Non-blocking — safe to call inside an async generator.
    """
    k = _key(artist_name)
    if k in _known:
        logger.debug("[queue] Already known, skipping: %s", artist_name)
        return False
    try:
        _queue.put_nowait(artist_name)
        _known.add(k)
        _pending.append(artist_name)
        _enqueue_log.appendleft({
            "artist":    artist_name,
            "enqueued_at": _now_iso(),
            "queue_depth": _queue.qsize(),
        })
        logger.info(
            "[queue] ✚ Enqueued '%s'  (pending: %d)",
            artist_name, _queue.qsize(),
        )
        return True
    except asyncio.QueueFull:
        logger.warning("[queue] Queue full (%d), dropping: %s", _MAX_QUEUE_SIZE, artist_name)
        return False


# ── Status helpers (used by the admin endpoint) ───────────────────────────────

def get_queue() -> asyncio.Queue[str]:
    return _queue


def get_status() -> dict:
    return {
        "queue_size":    _queue.qsize(),
        "pending":       list(_pending),
        "recent_enqueues": list(_enqueue_log),
    }
