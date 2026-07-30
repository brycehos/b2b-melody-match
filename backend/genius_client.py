"""
Genius lyrics client — uses the official authenticated Genius REST API for
song search, then scrapes the Genius lyrics page directly.

Why not lyricsgenius?
  lyricsgenius.search_song() internally calls genius.com/api/search/multi
  (the *public* unauthenticated endpoint) which now returns 403 for all
  third-party clients.  The *authenticated* endpoint api.genius.com/search
  still works fine.  We replicate exactly what lyricsgenius does internally
  but route search through the right endpoint.
"""

from __future__ import annotations

import os
import re
import time

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

_SEARCH_URL = "https://api.genius.com/search"
_TIMEOUT    = 15    # seconds per request
_HEADERS: dict[str, str] = {}   # populated lazily with the Bearer token


def _auth_headers() -> dict[str, str]:
    global _HEADERS
    if not _HEADERS:
        token = os.getenv("GENIUS_ACCESS_TOKEN", "")
        if not token:
            raise RuntimeError(
                "GENIUS_ACCESS_TOKEN is not set in .env — "
                "get one at genius.com/api-clients"
            )
        _HEADERS = {"Authorization": f"Bearer {token}"}
    return _HEADERS


def validate_token() -> None:
    """
    Verify the token works before starting a long seeding run.
    Raises RuntimeError with a clear message on failure so the caller can
    abort immediately rather than silently collecting 0 lyrics for every song.

    Note: we validate against /search, NOT /account.  Client access tokens
    (the kind generated at genius.com/api-clients) are authorized for /search
    but return 401 on /account, which requires a user-scoped OAuth token.
    Checking /account would falsely reject a perfectly working token.
    """
    try:
        resp = requests.get(
            _SEARCH_URL,
            headers=_auth_headers(),
            params={"q": "test"},
            timeout=10,
        )
    except Exception as e:
        raise RuntimeError(f"Could not reach Genius API: {e}") from e

    if resp.status_code == 401:
        raise RuntimeError(
            "GENIUS_ACCESS_TOKEN is expired or revoked.\n"
            "  1. Go to https://genius.com/api-clients\n"
            "  2. Open your app → click 'Generate Access Token'\n"
            "  3. Paste the new token into backend/.env as GENIUS_ACCESS_TOKEN=...\n"
            "  4. Re-run the seed script."
        )
    if not resp.ok:
        raise RuntimeError(
            f"Genius API returned unexpected status {resp.status_code}: {resp.text[:200]}"
        )


def _search_genius(query: str) -> list[dict]:
    """Hit api.genius.com/search and return a list of hit result dicts."""
    try:
        resp = requests.get(
            _SEARCH_URL,
            headers=_auth_headers(),
            params={"q": query},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("response", {}).get("hits", [])
    except Exception:
        return []


def _scrape_lyrics(url: str) -> str | None:
    """
    Download a Genius song page and extract the lyrics text.

    Modern Genius pages mark their lyrics containers with
    data-lyrics-container="true".  We replace <br> tags with newlines,
    strip all other markup, and join the containers.
    """
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={
            # Genius blocks bare requests; a minimal user-agent is enough
            "User-Agent": "Mozilla/5.0 (compatible; MelodyMatchBot/1.0)"
        })
        if not resp.ok:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        containers = soup.find_all("div", {"data-lyrics-container": "true"})
        if not containers:
            return None
        parts: list[str] = []
        for div in containers:
            for br in div.find_all("br"):
                br.replace_with("\n")
            parts.append(div.get_text())
        return "\n".join(parts).strip() or None
    except Exception:
        return None


def get_lyrics(title: str, artist: str) -> str | None:
    """
    Return cleaned lyrics for the given song, or None if not found.

    Strategy:
      1. Search api.genius.com/search for "{title} {artist}"
      2. Walk the top-3 hits, pick the first where the credited artist name
         loosely matches our artist string
      3. Scrape the lyrics page; retry once on network hiccup
    """
    hits = _search_genius(f"{title} {artist}")
    if not hits:
        return None

    # Pick the best-matching hit
    artist_lower = artist.lower()
    song_url: str | None = None

    for hit in hits[:5]:
        if hit.get("type") != "song":
            continue
        result   = hit["result"]
        credited = result.get("primary_artist", {}).get("name", "").lower()
        if artist_lower in credited or credited in artist_lower:
            song_url = result.get("url")
            break

    # If no artist match, fall back to the top result
    if not song_url and hits:
        song_url = hits[0]["result"].get("url")

    if not song_url:
        return None

    lyrics = _scrape_lyrics(song_url)
    if lyrics and len(lyrics) > 100:
        return _clean(lyrics)
    return None


def _clean(raw: str) -> str:
    """Remove Genius boilerplate injected around the lyrics text."""
    # Strip contributor count / title header: "23 ContributorsSong Name Lyrics"
    cleaned = re.sub(
        r"^\d+\s+Contributors?\s*.*?Lyrics\s*",
        "",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip the "About" blurb Genius injects before the lyrics, which ends with
    # "…Read More".  Only strip when it appears before the first section marker
    # (e.g. "[Verse 1]") so we never eat actual lyric lines containing the phrase.
    first_bracket = cleaned.find("[")
    read_more = cleaned.find("Read More")
    if read_more != -1 and (first_bracket == -1 or read_more < first_bracket):
        cleaned = cleaned[read_more + len("Read More"):]
    # Strip trailing "You might also like" and/or Embed tag
    cleaned = re.sub(r"You might also like.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\d*\s*Embed\s*$", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()
