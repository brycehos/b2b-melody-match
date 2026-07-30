"""
iTunes Search API client — no authentication or API key required.

Provides artist-based track search with album art (up to 600×600) and
30-second preview URLs. Used by the seed script to populate Pinecone.

Reference: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/
Rate limit: ~20 requests/minute; the seed script sleeps between calls.
"""

import json
import ssl
import time
import urllib.parse
import urllib.request
from typing import Optional

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


def search_tracks_by_artist(artist: str, limit: int = 10) -> list[dict]:
    """
    Search iTunes for songs by a specific artist.

    Uses the ``artistTerm`` attribute so results are scoped to the artist
    name, not just any field. Returns raw iTunes result dicts (kind=song only).
    """
    params = urllib.parse.urlencode({
        "term":      artist,
        "entity":    "song",
        "media":     "music",
        "attribute": "artistTerm",
        "limit":     min(limit, 200),  # iTunes hard max = 200
        "country":   "US",
    })
    url = f"https://itunes.apple.com/search?{params}"

    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=12, context=_SSL_CONTEXT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            # Filter to only song-type results (not podcasts, audiobooks, etc.)
            return [r for r in data.get("results", []) if r.get("kind") == "song"]
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError(f"iTunes search forbidden for '{artist}'") from e
            if attempt == 2:
                raise RuntimeError(f"iTunes search failed for '{artist}': {e}") from e
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"iTunes search failed for '{artist}': {e}") from e
            time.sleep(2 ** attempt)

    return []


def high_res_artwork(url: Optional[str]) -> Optional[str]:
    """Upgrade a 100×100 (or 60×60) iTunes artwork URL to 600×600."""
    if not url:
        return None
    return (
        url.replace("100x100bb", "600x600bb")
           .replace("60x60bb",  "600x600bb")
    )


def external_url(artist_name: str, track_name: str) -> str:
    """
    Construct a Spotify search URL for the song.
    Opens Spotify's search page — works for any Spotify user (free or paid).
    """
    term = urllib.parse.quote(f"{artist_name} {track_name}")
    return f"https://open.spotify.com/search/{term}"


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"
