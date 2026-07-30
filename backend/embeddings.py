import os
import time
import voyageai
from dotenv import load_dotenv

load_dotenv()

_client: voyageai.Client | None = None

# How long to wait between retries when rate-limited.
# At Voyage AI's free-tier limit (3 RPM), each request can't happen more often
# than once per 20s. We use 25s to give a comfortable buffer.
_RATE_LIMIT_WAIT_SECONDS = 25
_MAX_RETRIES = 5


def get_client() -> voyageai.Client:
    global _client
    if _client is None:
        _client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
    return _client


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "rate" in msg or "429" in msg or "payment" in msg or "ratelimit" in msg


def _rate_limit_hint() -> str:
    return (
        "Add a payment method at https://dashboard.voyageai.com/ "
        "(200M free tokens still apply — this just unlocks full rate limits)"
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of documents. Retries with linear back-off on rate-limit errors.
    At Voyage AI's free-tier limit (3 RPM) the script will slow down but not crash.
    Add a payment method at dashboard.voyageai.com to unlock full rate limits.
    """
    client = get_client()
    for attempt in range(_MAX_RETRIES):
        try:
            result = client.embed(texts, model="voyage-3", input_type="document")
            return result.embeddings
        except Exception as e:
            if _is_rate_limit(e):
                if attempt == _MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Voyage AI rate limit exhausted after {_MAX_RETRIES} retries.\n"
                        f"  → {_rate_limit_hint()}"
                    ) from e
                wait = _RATE_LIMIT_WAIT_SECONDS * (attempt + 1)  # 25, 50, 75, 100s
                print(
                    f"\n    ⏳ Voyage AI rate limit hit — waiting {wait}s "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}).\n"
                    f"       Tip: {_rate_limit_hint()}\n"
                )
                time.sleep(wait)
            else:
                raise
    return []  # unreachable


def embed_query(text: str) -> list[float]:
    """
    Embed a single search query. Retries with linear back-off on rate-limit errors.
    """
    client = get_client()
    for attempt in range(_MAX_RETRIES):
        try:
            result = client.embed([text], model="voyage-3", input_type="query")
            return result.embeddings[0]
        except Exception as e:
            if _is_rate_limit(e):
                if attempt == _MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Voyage AI rate limit exhausted after {_MAX_RETRIES} retries.\n"
                        f"  → {_rate_limit_hint()}"
                    ) from e
                wait = _RATE_LIMIT_WAIT_SECONDS * (attempt + 1)
                print(
                    f"\n    ⏳ Voyage AI rate limit hit — waiting {wait}s "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES}).\n"
                    f"       Tip: {_rate_limit_hint()}\n"
                )
                time.sleep(wait)
            else:
                raise
    return []  # unreachable


def _pick(value: float, buckets: list[tuple[float, str]], default: str) -> str:
    """Return the label of the first bucket whose threshold the value exceeds."""
    for threshold, label in buckets:
        if value > threshold:
            return label
    return default


def generate_audio_description(features: dict, track_name: str, artist: str, genre: str) -> str:
    """
    Convert numeric audio features into a rich natural-language description
    for embedding.  Finer-grained buckets and varied musical vocabulary give
    the embedding model more signal to distinguish songs — coarse three-bucket
    labels made thousands of songs share near-identical text, which compressed
    similarity scores and made mood queries feel inflexible.
    """
    energy_v  = float(features.get("energy", 0.5))
    tempo_v   = float(features.get("tempo", 110))
    valence_v = float(features.get("valence", 0.5))
    dance_v   = float(features.get("danceability", 0.5))
    acous_v   = float(features.get("acousticness", 0.5))
    instr_v   = float(features.get("instrumentalness", 0.1))
    speech_v  = float(features.get("speechiness", 0.05))
    loud_v    = float(features.get("loudness", -8.0))
    live_v    = float(features.get("liveness", 0.15))
    mode_v    = int(features.get("mode", 1))

    energy = _pick(energy_v, [
        (0.85, "explosive high-intensity"),
        (0.70, "energetic driving"),
        (0.55, "moderately energetic"),
        (0.40, "relaxed mid-tempo"),
        (0.25, "mellow laid-back"),
    ], "calm quiet subdued")

    tempo = _pick(tempo_v, [
        (160, f"very fast rapid {int(tempo_v)} BPM"),
        (140, f"fast uptempo {int(tempo_v)} BPM"),
        (118, f"moderate steady {int(tempo_v)} BPM"),
        (95,  f"mid-tempo grooving {int(tempo_v)} BPM"),
        (75,  f"slow unhurried {int(tempo_v)} BPM"),
    ], f"very slow ballad pace {int(tempo_v)} BPM")

    mood = _pick(valence_v, [
        (0.80, "euphoric joyful uplifting"),
        (0.62, "upbeat happy feel-good"),
        (0.45, "bittersweet reflective"),
        (0.30, "melancholic wistful"),
    ], "sad somber sorrowful")

    tonality = "major key, bright hopeful tonality" if mode_v == 1 else "minor key, dark moody tonality"

    dance = _pick(dance_v, [
        (0.75, "highly danceable with an infectious groove"),
        (0.55, "danceable rhythmic"),
        (0.40, "gently rhythmic"),
    ], "free-flowing, not dance-oriented")

    sound = _pick(acous_v, [
        (0.75, "organic acoustic instrumentation, unplugged natural sound"),
        (0.50, "mostly acoustic with warm natural textures"),
        (0.25, "blend of acoustic and electronic elements"),
    ], "electronic produced sound with synthesized textures")

    if instr_v > 0.7:
        voice = "purely instrumental, no vocals"
    elif instr_v > 0.4:
        voice = "mostly instrumental with sparse vocals"
    elif speech_v > 0.30:
        voice = "spoken-word delivery, rap vocals, rhythmic wordplay"
    elif speech_v > 0.15:
        voice = "vocal-led with rhythmic, speech-like phrasing"
    else:
        voice = "melodic sung vocals"

    loud = _pick(loud_v, [
        (-5.0,  "loud powerful production"),
        (-9.0,  "full balanced production"),
        (-14.0, "soft intimate production"),
    ], "very quiet delicate production")

    live = "Live performance energy with audience ambience. " if live_v > 0.6 else ""

    genre_part = f"{genre} " if genre else ""
    if track_name and artist:
        credit = f" Song: '{track_name}' by {artist}."
    elif artist:
        credit = f" Artist: {artist}."
    else:
        credit = ""

    return (
        f"{genre_part}music, {energy} feel at a {tempo} tempo. "
        f"{mood.capitalize()} mood, {tonality}. "
        f"{voice.capitalize()}, {dance}. "
        f"{sound.capitalize()}, {loud}. {live}"
        f"{credit}"
    ).strip()
