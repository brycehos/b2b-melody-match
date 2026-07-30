"""
Backfill lyrics vectors for songs that already have audio vectors in Pinecone.

The seed script skips any track whose audio vector already exists, so songs
indexed before the Genius client was fixed never got their lyrics added.
This script closes that gap without re-seeding:

  1. List every vector ID in the audio namespace
  2. Diff against the lyrics namespace AND a local checkpoint file to find
     songs still needing a lyrics lookup
  3. For each: fetch title/artist metadata → Genius lyrics → Voyage AI
     embedding → upsert to the lyrics namespace

Resumability
────────────
Two mechanisms let this pick up exactly where it left off after a crash,
network timeout, or the laptop sleeping/logging out:

  • Pinecone re-diff — songs that already have a lyrics vector are skipped.
  • Checkpoint file (scripts/.lyrics_backfill_progress.txt) — an append-only
    log of every song_id we've *finished processing*, including songs that
    turned out to have NO usable lyrics. Without this, every restart would
    re-query Genius for all the no-lyrics songs (the bulk of the slow work),
    because they never produce a vector to diff against.

The checkpoint is flushed to disk after every batch upsert and again on
graceful exit (Ctrl-C), so at most one in-flight batch of work is ever
repeated. Delete the checkpoint file to force a full re-run from scratch.

Usage:
    cd backend
    .venv/bin/python3 scripts/backfill_lyrics.py            # full run
    .venv/bin/python3 scripts/backfill_lyrics.py --limit 50 # test on 50 songs
    .venv/bin/python3 scripts/backfill_lyrics.py --reset    # ignore checkpoint
"""

import argparse
import sys
import time
from pathlib import Path

# Allow imports from the backend package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings as emb
import genius_client as gc
import pinecone_client as pc

FETCH_BATCH   = 100   # Pinecone fetch() batch size
UPSERT_EVERY  = 20    # upsert + checkpoint after this many lyrics collected
EMBED_BATCH   = 32    # Voyage AI batch size
GENIUS_DELAY  = 1.5   # seconds between Genius requests (free-tier safe)
MAX_LYRICS_CHARS = 3000

CHECKPOINT_FILE = Path(__file__).resolve().parent / ".lyrics_backfill_progress.txt"


def list_all_ids(index, namespace: str) -> set[str]:
    """Enumerate every vector ID in a namespace via the paginated list API."""
    ids: set[str] = set()
    for page in index.list(namespace=namespace, limit=99):
        ids.update(page)
    return ids


def load_checkpoint() -> set[str]:
    """Return the set of song_ids already fully processed in a previous run."""
    if not CHECKPOINT_FILE.exists():
        return set()
    with CHECKPOINT_FILE.open("r", encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip()}


def append_checkpoint(song_ids: list[str]) -> None:
    """Durably record song_ids as processed (append + fsync so a hard kill can't lose them)."""
    if not song_ids:
        return
    import os
    with CHECKPOINT_FILE.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(song_ids) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill lyrics vectors")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process this many songs (0 = all)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignore and delete the checkpoint file, starting fresh")
    args = parser.parse_args()

    print("🎤 MelodyMatch Lyrics Backfill  (Pinecone → Genius → Voyage AI)")
    print("=" * 60)

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("  ↺ Checkpoint reset — starting from scratch\n")

    print("Validating Genius API token…")
    gc.validate_token()
    print("  ✓ Genius token works\n")

    index = pc.get_index()

    print("Listing audio namespace…")
    audio_ids = list_all_ids(index, pc.NAMESPACE_AUDIO)
    print(f"  {len(audio_ids)} audio vectors")

    print("Listing lyrics namespace…")
    lyrics_ids = list_all_ids(index, pc.NAMESPACE_LYRICS)
    print(f"  {len(lyrics_ids)} lyrics vectors")

    checkpoint = load_checkpoint()
    if checkpoint:
        print(f"  {len(checkpoint)} songs already processed (from checkpoint)")

    # A song still needs work only if it has no lyrics vector AND isn't in the
    # checkpoint (which also covers songs we confirmed have no usable lyrics).
    have_lyrics = {vid.removesuffix("_lyrics") for vid in lyrics_ids}
    done = have_lyrics | checkpoint
    missing = sorted(
        vid for vid in audio_ids
        if vid.removesuffix("_audio") not in done
    )
    print(f"  → {len(missing)} songs still need a lyrics lookup\n")

    if args.limit:
        missing = missing[: args.limit]
        print(f"  (limited to {len(missing)} songs via --limit)\n")

    if not missing:
        print("Nothing to do — every song has been processed. ✓")
        return

    total_found = 0
    total_skipped = 0
    total_upserted = 0
    # Buffers hold work not yet durably persisted. song_id is tracked alongside
    # so we can checkpoint exactly what was flushed.
    pending_texts: list[str] = []
    pending_meta:  list[dict] = []
    pending_song_ids: list[str] = []
    # song_ids confirmed to have no usable lyrics, awaiting the next checkpoint write
    no_lyrics_pending: list[str] = []

    def flush_buffer() -> None:
        """Embed + upsert buffered lyrics, then checkpoint everything processed since the last flush."""
        nonlocal total_upserted
        if pending_texts:
            vectors = []
            for i in range(0, len(pending_texts), EMBED_BATCH):
                embs = emb.embed_texts(pending_texts[i : i + EMBED_BATCH])
                for j, e in enumerate(embs):
                    entry = pending_meta[i + j]
                    vectors.append({
                        "id": entry["id"], "values": e, "metadata": entry["metadata"],
                    })
            pc.upsert_vectors(vectors, pc.NAMESPACE_LYRICS)
            total_upserted += len(vectors)

        # Checkpoint AFTER the upsert succeeds so we never mark a song done
        # before its vector is actually in Pinecone.
        append_checkpoint(pending_song_ids + no_lyrics_pending)
        pending_texts.clear()
        pending_meta.clear()
        pending_song_ids.clear()
        no_lyrics_pending.clear()

    try:
        for batch_start in range(0, len(missing), FETCH_BATCH):
            batch_ids = missing[batch_start : batch_start + FETCH_BATCH]
            fetched = index.fetch(ids=batch_ids, namespace=pc.NAMESPACE_AUDIO)
            vec_map = getattr(fetched, "vectors", None) or {}

            for vid in batch_ids:
                song_id = vid.removesuffix("_audio")
                vec = vec_map.get(vid)
                if vec is None:
                    # No audio vector to read metadata from — mark done so we
                    # don't keep retrying it on every run.
                    total_skipped += 1
                    no_lyrics_pending.append(song_id)
                    continue
                meta = dict(vec.metadata or {})
                title, artist = meta.get("title", ""), meta.get("artist", "")
                if not title or not artist:
                    total_skipped += 1
                    no_lyrics_pending.append(song_id)
                    continue

                lyrics = gc.get_lyrics(title, artist)
                time.sleep(GENIUS_DELAY)

                if not lyrics or len(lyrics) <= 100:
                    total_skipped += 1
                    no_lyrics_pending.append(song_id)
                else:
                    total_found += 1
                    meta["namespace"] = "lyrics"
                    pending_texts.append(lyrics[:MAX_LYRICS_CHARS])
                    pending_meta.append({"id": f"{song_id}_lyrics", "metadata": meta})
                    pending_song_ids.append(song_id)

                checked = total_found + total_skipped
                if checked % 10 == 0:
                    print(f"  {checked}/{len(missing)} checked — {total_found} lyrics found")

                # Persist once enough lyrics accumulate so an interruption
                # loses at most one in-flight batch of Genius lookups.
                if len(pending_texts) >= UPSERT_EVERY:
                    flush_buffer()
                    print(f"    ⬆ upserted + checkpointed "
                          f"(running total: {total_upserted} lyrics vectors)")
    except KeyboardInterrupt:
        print("\n⏸  Interrupted — flushing progress so far…")
        flush_buffer()
        print(f"   Saved. Re-run to resume from here "
              f"({total_upserted} lyrics vectors added this run).")
        return
    finally:
        # Persist any straggler no-lyrics checkpoints even if nothing was upserted
        if pending_texts or pending_song_ids or no_lyrics_pending:
            flush_buffer()

    print("=" * 60)
    print(f"✅ Done: {total_upserted} lyrics vectors added, "
          f"{total_skipped} songs had no usable lyrics")


if __name__ == "__main__":
    main()
