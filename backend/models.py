from pydantic import BaseModel, Field
from typing import Literal, Optional

# ── Plan constants ────────────────────────────────────────────────────────────

SEARCH_LIMITS: dict[str, int] = {
    "anonymous": 3,   # client-side only
    "free":      10,
    "explorer":  75,
    "unlimited": 300,
}

PAID_PLANS = {"explorer", "unlimited"}
CATALOG_GATED_PLANS = {"anonymous", "free"}  # restricted to popular tier


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    search_type: Literal["melody", "lyrics", "both"] = "both"


class AudioFeatures(BaseModel):
    energy: float
    tempo: float
    valence: float
    danceability: float
    acousticness: float
    instrumentalness: float
    speechiness: float
    loudness: float
    key: int
    mode: int
    liveness: float


class SongResult(BaseModel):
    song_id: str
    title: str
    artist: str
    album: str
    year: int
    genre: str
    duration: str
    similarity: float
    match_reason: Optional[str] = None
    preview_url: Optional[str] = None
    image_url: Optional[str] = None
    spotify_url: Optional[str] = None
    audio_features: Optional[AudioFeatures] = None


class AgentEvent(BaseModel):
    type: Literal["thinking", "tool_call", "tool_result", "result", "error"]
    text: Optional[str] = None
    tool: Optional[str] = None
    query: Optional[str] = None
    count: Optional[int] = None
    songs: Optional[list[SongResult]] = None
    explanation: Optional[str] = None
