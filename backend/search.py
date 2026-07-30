from embeddings import embed_query
from pinecone_client import query_vectors, NAMESPACE_AUDIO, NAMESPACE_LYRICS
from models import SongResult, AudioFeatures

# Voyage AI (voyage-3) cosine similarity lands in a narrow band that never
# approaches 1.0 — real matches cluster around 0.50–0.60 — so showing raw values
# as percentages is both misleadingly low AND poorly differentiated. Instead we
# map each namespace's *meaningful window* [lo, hi] onto a readable display band
# [_DISPLAY_MIN, _DISPLAY_MAX], which spreads the compressed raw scores out so
# top results read high while weaker results stay visibly lower. Windows are set
# from observed score distributions; lyrics vs. a short theme query top out lower
# than short audio-description matches, so it gets a lower window.
_AUDIO_WINDOW  = (0.42, 0.60)
_LYRICS_WINDOW = (0.40, 0.55)
_DISPLAY_MIN   = 0.55
_DISPLAY_MAX   = 0.99


def _calibrate_score(raw: float, window: tuple[float, float] = _AUDIO_WINDOW) -> float:
    """Map a raw cosine similarity through a namespace window to a 0.55–0.99 display score."""
    lo, hi = window
    frac = (raw - lo) / (hi - lo) if hi > lo else 0.0
    frac = min(1.0, max(0.0, frac))
    return round(_DISPLAY_MIN + frac * (_DISPLAY_MAX - _DISPLAY_MIN), 3)


def _match_to_song(match: dict, window: tuple[float, float] | None = _AUDIO_WINDOW) -> SongResult:
    """
    Build a SongResult from a Pinecone match.

    window controls score display:
      • a (lo, hi) tuple → calibrate the raw cosine score through that window
      • None → the score is already a final display value; just round it
        (used by search_combined, which pre-calibrates per namespace before merging)
    """
    meta = match.get("metadata", {})

    # Audio features are stored as flattened top-level keys (af_*) because
    # Pinecone doesn't support nested dict metadata values.
    audio_features = None
    if "af_energy" in meta:
        try:
            audio_features = AudioFeatures(
                energy=float(meta.get("af_energy", 0)),
                tempo=float(meta.get("af_tempo", 0)),
                valence=float(meta.get("af_valence", 0)),
                danceability=float(meta.get("af_danceability", 0)),
                acousticness=float(meta.get("af_acousticness", 0)),
                instrumentalness=float(meta.get("af_instrumentalness", 0)),
                speechiness=float(meta.get("af_speechiness", 0)),
                loudness=float(meta.get("af_loudness", 0)),
                key=int(meta.get("af_key", 0)),
                mode=int(meta.get("af_mode", 0)),
                liveness=float(meta.get("af_liveness", 0)),
            )
        except Exception:
            pass  # non-fatal — audio features are optional display data

    return SongResult(
        song_id=meta.get("song_id", match["id"]),
        title=meta.get("title", "Unknown"),
        artist=meta.get("artist", "Unknown"),
        album=meta.get("album", "Unknown"),
        year=int(meta.get("year", 0)),
        genre=meta.get("genre", "Unknown"),
        duration=meta.get("duration", "0:00"),
        similarity=(
            round(float(match.get("score", 0)), 3)
            if window is None
            else _calibrate_score(float(match.get("score", 0)), window)
        ),
        preview_url=meta.get("preview_url"),
        image_url=meta.get("image_url"),
        spotify_url=meta.get("spotify_url"),
        audio_features=audio_features,
    )


def _deduplicate(songs: list[SongResult]) -> list[SongResult]:
    seen: set[str] = set()
    unique = []
    for song in songs:
        if song.song_id not in seen:
            seen.add(song.song_id)
            unique.append(song)
    return unique


def _catalog_filter(restrict_to_popular: bool) -> dict | None:
    """Return a Pinecone metadata filter when catalog gating is active."""
    if restrict_to_popular:
        return {"catalog_tier": {"$eq": "popular"}}
    return None


def search_by_artist(
    artist_name: str, top_k: int = 10, restrict_to_popular: bool = False
) -> list[SongResult]:
    """
    Return songs by a specific artist using Pinecone metadata filtering.

    All vectors store the original artist name in the ``artist`` field and
    newer vectors also carry ``artist_lower`` (lowercase, for case-insensitive
    lookup).  We cover both with a ``$or`` filter so the query works on vectors
    indexed before artist_lower was added.

    The similarity score is overridden to 1.0 — these are exact artist matches,
    not approximate semantic matches, so showing 40 % would be misleading.
    """
    artist_key = artist_name.strip().lower()

    # Build case variations that survive Python's broken str.title() — e.g.
    # "her's".title() → "Her'S" (wrong), but capitalize() per word → "Her's" ✓
    _name = artist_name.strip()
    artist_variations: list[str] = list({
        _name,
        _name.lower(),
        " ".join(w.capitalize() for w in _name.split()),   # "her's" → "Her's"
    })

    # $or covers new vectors (artist_lower) and old vectors (artist, any case)
    filter_dict: dict = {
        "$or": [
            {"artist_lower": {"$eq": artist_key}},
            {"artist": {"$in": artist_variations}},
        ]
    }
    if restrict_to_popular:
        filter_dict = {"$and": [filter_dict, {"catalog_tier": {"$eq": "popular"}}]}

    # Use a generic query vector — the metadata filter does the real work.
    # Fetch top_k*3 to have buffer for deduplication across multiple index runs.
    vector = embed_query(f"music by {artist_name}")
    matches = query_vectors(vector, NAMESPACE_AUDIO, top_k=top_k * 3, filter=filter_dict)
    results = _deduplicate([_match_to_song(m) for m in matches])

    # Fallback: if the name didn't match any variation (case mismatch the
    # variations didn't cover), pull a large result set and filter client-side.
    if not results:
        broad = query_vectors(
            vector, NAMESPACE_AUDIO, top_k=500,
            filter=_catalog_filter(restrict_to_popular),
        )
        seen: set[str] = set()
        for m in broad:
            song = _match_to_song(m)
            if song.song_id not in seen and song.artist.strip().lower() == artist_key:
                results.append(song)
                seen.add(song.song_id)

    # Override similarity to 1.0 — exact artist matches, not semantic similarity.
    for song in results:
        song.similarity = 1.0

    return results[:top_k]


def search_by_audio_mood(
    query: str, top_k: int = 8, restrict_to_popular: bool = False
) -> list[SongResult]:
    vector = embed_query(query)
    matches = query_vectors(
        vector, NAMESPACE_AUDIO, top_k=top_k, filter=_catalog_filter(restrict_to_popular)
    )
    return _deduplicate([_match_to_song(m) for m in matches])


def search_by_lyrics_theme(
    query: str, top_k: int = 8, restrict_to_popular: bool = False
) -> list[SongResult]:
    vector = embed_query(query)
    matches = query_vectors(
        vector, NAMESPACE_LYRICS, top_k=top_k, filter=_catalog_filter(restrict_to_popular)
    )
    return _deduplicate([_match_to_song(m, window=_LYRICS_WINDOW) for m in matches])


def search_combined(
    audio_query: str,
    lyrics_query: str,
    audio_weight: float = 0.5,
    top_k: int = 8,
    restrict_to_popular: bool = False,
) -> list[SongResult]:
    lyrics_weight = 1.0 - audio_weight
    fetch_k = min(top_k * 2, 20)
    cat_filter = _catalog_filter(restrict_to_popular)

    audio_vector = embed_query(audio_query)
    lyrics_vector = embed_query(lyrics_query)

    audio_matches = query_vectors(audio_vector, NAMESPACE_AUDIO, top_k=fetch_k, filter=cat_filter)
    lyrics_matches = query_vectors(lyrics_vector, NAMESPACE_LYRICS, top_k=fetch_k, filter=cat_filter)

    # Weighted average over the namespaces where each song actually matched.
    # Dividing by the contributing weight (not the total) matters: if a song
    # only matched in one namespace — or the lyrics namespace is sparse/empty —
    # a plain weighted sum would halve its score and make every combined
    # search look like a weak match.
    weighted_sum: dict[str, float] = {}
    weight_total: dict[str, float] = {}
    meta_map: dict[str, dict] = {}

    # Scores are calibrated per namespace BEFORE merging (audio and lyrics have
    # different windows), so the weighted average is in comparable display units
    # and _match_to_song must not recalibrate (window=None → just round).
    for m in audio_matches:
        sid = m["metadata"].get("song_id", m["id"])
        cal = _calibrate_score(float(m["score"]), _AUDIO_WINDOW)
        weighted_sum[sid] = weighted_sum.get(sid, 0.0) + cal * audio_weight
        weight_total[sid] = weight_total.get(sid, 0.0) + audio_weight
        meta_map[sid] = m

    for m in lyrics_matches:
        sid = m["metadata"].get("song_id", m["id"])
        cal = _calibrate_score(float(m["score"]), _LYRICS_WINDOW)
        weighted_sum[sid] = weighted_sum.get(sid, 0.0) + cal * lyrics_weight
        weight_total[sid] = weight_total.get(sid, 0.0) + lyrics_weight
        if sid not in meta_map:
            meta_map[sid] = m

    scores = {
        sid: weighted_sum[sid] / weight_total[sid]
        for sid in weighted_sum
        if weight_total[sid] > 0
    }

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    results = []
    for sid, combined_score in ranked:
        match = meta_map[sid].copy()
        match["score"] = combined_score
        results.append(_match_to_song(match, window=None))

    return results
