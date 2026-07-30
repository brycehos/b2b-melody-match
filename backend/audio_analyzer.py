"""
Audio analysis module for Shazam-like matching.

Given raw audio bytes (WAV, MP3, M4A, OGG, etc.), extracts sonic features
comparable to Spotify's audio-feature set, then converts them to a natural-
language description that can be embedded by Voyage AI and searched against
the Pinecone `audio` namespace — the same embedding space used by the rest of
the catalog.

Dependencies: librosa, soundfile, numpy  (all in requirements.txt)
ffmpeg must be installed in the runtime environment for MP3/M4A/OGG decoding.
"""

from __future__ import annotations

import io
import logging
import math
import tempfile
import os

import numpy as np

logger = logging.getLogger(__name__)

# Maximum number of seconds to analyse (keeps latency bounded for long clips)
MAX_AUDIO_SECONDS = 60


def _load_audio(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """
    Load raw audio bytes into a mono float32 numpy array.

    Tries soundfile first (zero overhead for WAV/FLAC).  Falls back to
    librosa's ffmpeg-backed loader for compressed formats (MP3, M4A, OGG …).
    Returns (y, sr) where y is a 1-D float32 array and sr is the sample rate.
    """
    import soundfile as sf
    import librosa

    # --- Try soundfile (fast, supports WAV/FLAC/OGG natively) ---------------
    try:
        y, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
        if y.ndim == 2:          # multi-channel → mono
            y = y.mean(axis=1)
        return y, int(sr)
    except Exception:
        pass

    # --- Fall back to librosa + ffmpeg ----------------------------------------
    # Detect format from magic bytes so ffmpeg gets a recognisable extension.
    magic = audio_bytes[:4]
    if magic == b'RIFF':
        suffix = ".wav"
    elif magic == b'OggS':
        suffix = ".ogg"
    elif magic[:3] in (b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
        suffix = ".mp3"
    elif magic == b'fLaC':
        suffix = ".flac"
    elif magic == b'\x1a\x45\xdf\xa3':
        suffix = ".webm"
    else:
        suffix = ".webm"   # most common MediaRecorder output in Chrome

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        y, sr = librosa.load(tmp_path, sr=None, mono=True, dtype=np.float32)
        return y, int(sr)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _trim_to_max(y: np.ndarray, sr: int) -> np.ndarray:
    """Keep at most MAX_AUDIO_SECONDS of audio."""
    max_samples = MAX_AUDIO_SECONDS * sr
    if len(y) > max_samples:
        # Take the middle portion (intros are often silent / atypical)
        start = (len(y) - max_samples) // 2
        y = y[start : start + max_samples]
    return y


def _safe_float(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi] and guard against NaN/Inf."""
    if not math.isfinite(value):
        return (lo + hi) / 2
    return max(lo, min(hi, value))


def analyze_audio(audio_bytes: bytes) -> dict:
    """
    Extract Spotify-style audio features from raw audio bytes.

    Returns a dict with keys matching the Spotify audio-features schema used
    by the rest of the pipeline:
        energy, tempo, valence, danceability, acousticness,
        instrumentalness, speechiness, loudness, key, mode, liveness

    All values are intentionally approximate — the goal is to land in the
    right region of the embedding space, not to replicate Spotify's ML models.
    """
    import librosa

    y, sr = _load_audio(audio_bytes)
    y = _trim_to_max(y, sr)

    # ── RMS energy ───────────────────────────────────────────────────────────
    rms = float(np.sqrt(np.mean(y ** 2)))
    # Map RMS (typically 0.01–0.3) → [0, 1] with a sigmoid-ish curve
    energy = _safe_float(1 / (1 + math.exp(-10 * (rms - 0.08))))

    # ── Loudness (dBFS) ──────────────────────────────────────────────────────
    loudness_db = float(20 * math.log10(rms + 1e-9))   # roughly −60 to 0 dB
    loudness = max(-60.0, min(0.0, loudness_db))

    # ── Tempo (BPM) ──────────────────────────────────────────────────────────
    tempo_arr, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.squeeze(tempo_arr)) if np.ndim(tempo_arr) == 0 else float(tempo_arr[0])
    if not math.isfinite(tempo) or tempo < 30:
        tempo = 90.0   # safe fallback for very quiet / percussionless clips

    # ── Spectral centroid → brightness proxy for valence / acousticness ──────
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    mean_centroid = float(np.mean(centroid))
    # Low centroid (~500 Hz) = warm/acoustic/sad ; high (~3000 Hz) = bright/happy
    bright = _safe_float((mean_centroid - 500) / 2500)

    # ── Spectral rolloff → how much high-frequency energy exists ─────────────
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)
    mean_rolloff = float(np.mean(rolloff))
    rolloff_norm = _safe_float(mean_rolloff / (sr / 2))   # normalise to Nyquist

    # ── Zero-crossing rate → noisiness / speechiness proxy ───────────────────
    zcr = librosa.feature.zero_crossing_rate(y)
    mean_zcr = float(np.mean(zcr))
    # Typical ranges: ~0.05 speech, ~0.10 music, ~0.25 noise
    speechiness = _safe_float(mean_zcr * 4)

    # ── MFCCs → timbral texture ───────────────────────────────────────────────
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_var = float(np.mean(np.var(mfccs, axis=1)))
    # High variance = complex, varied timbre → less acoustic
    acousticness = _safe_float(1.0 - min(mfcc_var / 500, 1.0))

    # ── Chroma → key + mode ───────────────────────────────────────────────────
    chromagram = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chromagram, axis=1)
    key = int(np.argmax(chroma_mean))   # 0=C, 1=C#, …, 11=B

    # Simplified major/minor detection via template correlation
    major_template = np.array([1,0,1,0,1,1,0,1,0,1,0,1], dtype=float)
    minor_template = np.array([1,0,1,1,0,1,0,1,1,0,1,0], dtype=float)

    def _corr(template: np.ndarray, root: int) -> float:
        rolled = np.roll(template, root)
        denom = np.linalg.norm(chroma_mean) * np.linalg.norm(rolled)
        return float(np.dot(chroma_mean, rolled) / (denom + 1e-9))

    major_score = max(_corr(major_template, k) for k in range(12))
    minor_score = max(_corr(minor_template, k) for k in range(12))
    mode = 1 if major_score >= minor_score else 0   # 1 = major, 0 = minor

    # ── Danceability ─────────────────────────────────────────────────────────
    # Proxy: strong, regular beat + moderate-high tempo → danceable
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    pulse = librosa.beat.plp(onset_envelope=onset_env, sr=sr)
    beat_regularity = _safe_float(float(np.std(pulse)))
    tempo_norm = _safe_float((min(tempo, 170) - 60) / 110)   # [0,1] over 60–170 BPM
    danceability = _safe_float(0.5 * beat_regularity + 0.5 * tempo_norm)

    # ── Valence (perceived happiness) ────────────────────────────────────────
    # Major key + bright timbre + faster tempo → higher valence
    mode_bonus = 0.1 if mode == 1 else -0.1
    valence = _safe_float(0.4 * bright + 0.3 * tempo_norm + 0.3 * (0.5 + mode_bonus))

    # ── Instrumentalness ─────────────────────────────────────────────────────
    # Low ZCR + high MFCC smoothness → likely instrumental
    instrumentalness = _safe_float(1.0 - min(speechiness * 2, 1.0))

    # ── Liveness (crowd / reverb noise) ──────────────────────────────────────
    # High rolloff variance is a rough proxy for reverb / room noise
    rolloff_var = float(np.std(rolloff) / (np.mean(rolloff) + 1e-9))
    liveness = _safe_float(rolloff_var * 2)

    return {
        "energy":           round(energy, 4),
        "tempo":            round(tempo, 2),
        "valence":          round(valence, 4),
        "danceability":     round(danceability, 4),
        "acousticness":     round(acousticness, 4),
        "instrumentalness": round(instrumentalness, 4),
        "speechiness":      round(speechiness, 4),
        "loudness":         round(loudness, 2),
        "key":              key,
        "mode":             mode,
        "liveness":         round(liveness, 4),
    }
