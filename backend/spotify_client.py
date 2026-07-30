import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

_client: spotipy.Spotify | None = None


def get_client() -> spotipy.Spotify:
    global _client
    if _client is None:
        _client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=os.getenv("SPOTIFY_CLIENT_ID"),
                client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            )
        )
    return _client


def search_tracks(query: str, limit: int = 50) -> list[dict]:
    sp = get_client()
    results = sp.search(q=query, type="track", limit=limit)
    return results["tracks"]["items"]


def get_audio_features(track_ids: list[str]) -> list[dict | None]:
    sp = get_client()
    # Spotify allows up to 100 IDs per batch
    all_features = []
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i : i + 100]
        features = sp.audio_features(batch)
        all_features.extend(features)
    return all_features


def get_track(spotify_id: str) -> dict | None:
    sp = get_client()
    try:
        return sp.track(spotify_id)
    except Exception:
        return None


def get_playlist_tracks(playlist_id: str, limit: int = 100) -> list[dict]:
    sp = get_client()
    results = sp.playlist_tracks(playlist_id, limit=limit)
    tracks = []
    for item in results["items"]:
        if item and item.get("track"):
            tracks.append(item["track"])
    return tracks


def format_duration(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"
