"""
Seed MelodyMatch Pinecone index with songs via iTunes Search API + Genius.

iTunes Search API requires NO authentication — it works immediately with any
internet connection. Spotify's API is NOT used here (it now requires Premium
for the app owner even for basic search).

Audio features are fetched from Spotify when available. If that endpoint is
unavailable (deprecated Nov 2024 for most apps), genre-based defaults are used
so the script still produces well-differentiated audio embeddings.

Usage (from backend/ directory):
    python scripts/seed_songs.py

Requires a populated backend/.env file. Safe to re-run — skips songs already indexed.
"""

import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import itunes_client as itunes
import genius_client as gc
import embeddings as emb
import pinecone_client as pc

# ── Spotify client (optional — only for audio features) ──────────────────────
# If Spotify returns 403, we fall back to genre defaults transparently.
try:
    import spotify_client as _sp
    _SPOTIFY_AVAILABLE = True
except Exception:
    _SPOTIFY_AVAILABLE = False

# ── Genre → (artists, catalog_tier) ─────────────────────────────────────────
# iTunes search uses artistTerm attribute — no quota gating needed.
# "popular" → searchable by free/anonymous users
# "full"    → unlocked for Explorer / Unlimited subscribers

GENRE_ARTISTS: dict[str, tuple[list[str], str]] = {
    "pop": ([
        # Mega-mainstream
        "Taylor Swift", "Ed Sheeran", "Dua Lipa", "Harry Styles",
        "Billie Eilish", "Ariana Grande", "The Weeknd", "Bruno Mars",
        "Justin Bieber", "Katy Perry", "Lady Gaga", "Lizzo",
        "Olivia Rodrigo", "Charlie Puth", "Selena Gomez",
        # 2nd tier pop
        "Sam Smith", "Shawn Mendes", "Camila Cabello", "Halsey",
        "Lorde", "Sia", "Meghan Trainor", "Doja Cat", "Bebe Rexha",
        "Jason Derulo", "Miley Cyrus", "Troye Sivan", "Conan Gray",
        "Gracie Abrams", "Sabrina Carpenter", "Chappell Roan",
        # Pop classics
        "Michael Jackson", "Whitney Houston", "Madonna", "Mariah Carey",
        "George Michael", "Cyndi Lauper", "Prince", "Janet Jackson",
    ], "popular"),
    "rock": ([
        # Modern rock
        "Foo Fighters", "Green Day", "Arctic Monkeys", "Coldplay",
        "Twenty One Pilots", "Imagine Dragons", "The Killers",
        "Red Hot Chili Peppers", "Nirvana", "Weezer",
        "Muse", "Queens of the Stone Age", "The Strokes",
        # Classic rock
        "Led Zeppelin", "The Rolling Stones", "The Beatles", "Fleetwood Mac",
        "Pink Floyd", "AC/DC", "Aerosmith", "Guns N Roses",
        "Pearl Jam", "Soundgarden", "Alice in Chains", "Stone Temple Pilots",
        # Alt rock
        "Radiohead", "Blur", "Oasis", "The Smashing Pumpkins",
        "Beck", "R.E.M.", "The Cure", "Depeche Mode",
        "Jack White", "The White Stripes", "Cage the Elephant", "Portugal. The Man",
    ], "popular"),
    "hip-hop": ([
        # Current stars
        "Drake", "Kendrick Lamar", "J. Cole", "Travis Scott",
        "Cardi B", "Nicki Minaj", "Tyler the Creator", "Lil Nas X",
        "Megan Thee Stallion", "21 Savage", "Future", "Gunna",
        "Bad Bunny", "Jack Harlow", "Roddy Ricch",
        # Golden era / legends
        "Jay-Z", "Eminem", "Nas", "Kanye West",
        "Lil Wayne", "Rick Ross", "Snoop Dogg", "2Pac",
        "The Notorious B.I.G.", "DMX", "Outkast", "Ludacris",
        # Alternative / conscious
        "Chance the Rapper", "Logic", "Mac Miller", "Kid Cudi",
        "Childish Gambino", "Anderson Paak", "Isaiah Rashad", "Denzel Curry",
        "Run The Jewels", "Joey Bada$$", "Big Sean", "Wale",
    ], "popular"),
    "r&b": ([
        # Contemporary
        "Beyonce", "SZA", "Khalid", "Usher", "Alicia Keys",
        "Daniel Caesar", "Jhene Aiko", "Giveon", "Bryson Tiller",
        "Summer Walker", "Lucky Daye", "Ella Mai", "HER",
        # Legends
        "Marvin Gaye", "Stevie Wonder", "Aretha Franklin", "Whitney Houston",
        "Luther Vandross", "Anita Baker", "Janet Jackson", "Prince",
        # Neo-soul / indie R&B
        "Frank Ocean", "Miguel", "The Internet", "Syd",
        "Ari Lennox", "PJ Morton", "Brent Faiyaz", "Victoria Monet",
        "Kehlani", "Joyce Wrice", "UMI", "DVSN",
    ], "popular"),
    "country": ([
        # New mainstream
        "Morgan Wallen", "Luke Combs", "Chris Stapleton", "Kacey Musgraves",
        "Miranda Lambert", "Kenny Chesney", "Zac Brown Band",
        "Thomas Rhett", "Carrie Underwood", "Blake Shelton",
        "Eric Church", "Cody Johnson", "Lainey Wilson",
        # Classic country
        "Johnny Cash", "Dolly Parton", "Willie Nelson", "Merle Haggard",
        "Waylon Jennings", "Patsy Cline", "George Strait", "Alan Jackson",
        "Garth Brooks", "Tim McGraw", "Faith Hill", "Reba McEntire",
        # Country crossover
        "Sam Hunt", "Dan + Shay", "Florida Georgia Line", "Old Dominion",
        "Maren Morris", "Gabby Barrett", "Breland", "Darius Rucker",
    ], "popular"),
    "electronic": ([
        # House / techno
        "Daft Punk", "Calvin Harris", "Marshmello", "The Chainsmokers",
        "Kygo", "Flume", "Disclosure", "Four Tet", "Bonobo",
        "Aphex Twin", "Deadmau5", "Skrillex", "Zedd", "Caribou",
        # EDM / progressive
        "Martin Garrix", "Avicii", "David Guetta", "Tiesto",
        "Armin van Buuren", "Hardwell", "Alesso", "Vicetone",
        "Illenium", "Seven Lions", "Rezz", "ODESZA",
        # Ambient / downtempo
        "Brian Eno", "Moby", "Moderat", "Jon Hopkins",
        "Bicep", "Lane 8", "Tourist", "Tycho",
        # Bass music
        "Diplo", "Major Lazer", "GRiZ", "Gramatik",
    ], "full"),
    "jazz": ([
        # Bebop / hard bop
        "Miles Davis", "John Coltrane", "Bill Evans", "Dave Brubeck",
        "Thelonious Monk", "Herbie Hancock", "Chet Baker",
        "Charles Mingus", "Duke Ellington", "Louis Armstrong",
        "Wes Montgomery", "Oscar Peterson", "Charlie Parker",
        # Post-bop / fusion
        "Wayne Shorter", "McCoy Tyner", "Chick Corea", "Keith Jarrett",
        "Pat Metheny", "John Scofield", "Michael Brecker", "Joshua Redman",
        # Contemporary jazz
        "Kamasi Washington", "Thundercat", "Robert Glasper", "Esperanza Spalding",
        "Christian Scott", "Ambrose Akinmusire", "Makaya McCraven", "Nils Frahm",
    ], "full"),
    "classical": ([
        # Baroque
        "Johann Sebastian Bach", "Antonio Vivaldi", "George Frideric Handel",
        "Henry Purcell", "Claudio Monteverdi",
        # Classical period
        "Ludwig van Beethoven", "Wolfgang Amadeus Mozart", "Franz Schubert",
        "Joseph Haydn", "Carl Philipp Emanuel Bach",
        # Romantic
        "Frederic Chopin", "Franz Liszt", "Johannes Brahms",
        "Pyotr Ilyich Tchaikovsky", "Sergei Rachmaninoff",
        "Claude Debussy", "Maurice Ravel", "Gabriel Faure",
        # 20th century
        "Igor Stravinsky", "Dmitri Shostakovich", "Sergei Prokofiev",
        "Bela Bartok", "Aaron Copland", "Philip Glass", "Arvo Part",
    ], "full"),
    "metal": ([
        # Classic metal
        "Metallica", "Black Sabbath", "Iron Maiden", "Slayer",
        "Megadeth", "Pantera", "Judas Priest", "System of a Down",
        "Tool", "Avenged Sevenfold", "Lamb of God", "Mastodon",
        "Gojira", "Ghost", "Parkway Drive",
        # Thrash / death
        "Anthrax", "Testament", "Exodus", "Death",
        "Cannibal Corpse", "Morbid Angel", "Obituary", "Sepultura",
        # Prog / melodic
        "Dream Theater", "Opeth", "Meshuggah", "Between the Buried and Me",
        "Periphery", "Animals as Leaders", "Devin Townsend", "Arch Enemy",
        # Modern
        "Bring Me the Horizon", "Spiritbox", "Code Orange", "Knocked Loose",
    ], "full"),
    "folk": ([
        # Legends
        "Bob Dylan", "Joni Mitchell", "Neil Young", "Paul Simon",
        "Simon and Garfunkel", "Joan Baez", "Woody Guthrie", "Pete Seeger",
        # Indie folk
        "Fleet Foxes", "Bon Iver", "Iron and Wine", "The Avett Brothers",
        "Sufjan Stevens", "Nick Drake", "Mumford and Sons",
        "The Lumineers", "Lord Huron", "Father John Misty",
        # Contemporary folk
        "Phoebe Bridgers", "Julien Baker", "Lucy Dacus", "Adrianne Lenker",
        "Angel Olsen", "Hand Habits", "Weyes Blood", "Gregory Alan Isakov",
        "Iron and Wine", "Langhorne Slim", "Dar Williams", "Shawn Colvin",
    ], "full"),
    # ── New genres ──────────────────────────────────────────────────────────
    "latin": ([
        # Reggaeton / urban latino
        "J Balvin", "Maluma", "Ozuna", "Anuel AA",
        "Karol G", "Nicki Nicole", "Becky G", "Anitta",
        "Rauw Alejandro", "Jhay Cortez", "Lunay", "Farruko",
        # Pop latino
        "Shakira", "Ricky Martin", "Enrique Iglesias", "Marc Anthony",
        "Jennifer Lopez", "Gloria Estefan", "Camilo", "Sebastian Yatra",
        # Regional mexicano
        "Christian Nodal", "Natanael Cano", "Grupo Frontera", "Eslabón Armado",
        # Salsa / tropical
        "Celia Cruz", "Willie Colon", "Ruben Blades", "Marc Anthony",
    ], "popular"),
    "blues": ([
        # Delta / Chicago blues
        "B.B. King", "Muddy Waters", "Howlin Wolf", "Robert Johnson",
        "John Lee Hooker", "Buddy Guy", "Albert King", "Freddie King",
        "Elmore James", "Little Walter", "Sonny Boy Williamson", "Slim Harpo",
        # Blues rock
        "Stevie Ray Vaughan", "Gary Moore", "Joe Bonamassa", "Kenny Wayne Shepherd",
        "Johnny Winter", "Eric Clapton", "Peter Green", "Rory Gallagher",
        # Contemporary blues
        "Gary Clark Jr.", "Christone Kingfish Ingram", "Marcus King",
        "Fantastic Negrito", "Ruthie Foster", "Beth Hart",
    ], "full"),
    "reggae": ([
        # Roots reggae
        "Bob Marley", "Peter Tosh", "Bunny Wailer", "Toots and the Maytals",
        "Jimmy Cliff", "Dennis Brown", "Gregory Isaacs", "Burning Spear",
        "Culture", "Steel Pulse", "Third World", "Black Uhuru",
        # Dancehall / modern
        "Shabba Ranks", "Beenie Man", "Buju Banton", "Sizzla",
        "Sean Paul", "Shaggy", "Chronixx", "Protoje",
        "Koffee", "Jah Cure", "Pressure Busspipe", "Luciano",
    ], "full"),
    "indie": ([
        # Indie rock / alternative
        "Vampire Weekend", "Tame Impala", "Arcade Fire", "The National",
        "Modest Mouse", "Death Cab for Cutie", "Built to Spill", "Pavement",
        "Pixies", "Neutral Milk Hotel", "Wilco", "Yo La Tengo",
        # Indie pop
        "Belle and Sebastian", "Camera Obscura", "Of Montreal", "Beach House",
        "MGMT", "Wild Nothing", "Real Estate", "Washed Out",
        # Shoegaze / dream pop
        "My Bloody Valentine", "Slowdive", "Ride", "Mazzy Star",
        "Beach House", "Cigarettes After Sex", "Alvvays", "Men I Trust",
        # Lo-fi / bedroom pop
        "Rex Orange County", "Still Woozy", "Boy Pablo", "Clairo",
        "Snail Mail", "Japanese Breakfast", "Soccer Mommy", "Palehound",
    ], "full"),
}

# ── Genre-based audio feature fallbacks ─────────────────────────────────────
# Used when Spotify's audio-features endpoint is unavailable.
# Small random jitter is added per-track so vectors aren't identical.

GENRE_FEATURE_DEFAULTS: dict[str, dict] = {
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
    # New genres
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

TRACKS_PER_ARTIST = 15     # top tracks to request per artist search
BATCH_EMBED_SIZE  = 32
UPSERT_BATCH_SIZE = 100

# Set to True after the first audio-features 403 to stop spamming that endpoint
_audio_features_unavailable = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_unindexed_ids(track_ids: list[str]) -> list[str]:
    """Batch-fetch from Pinecone; return only IDs not yet indexed."""
    if not track_ids:
        return []
    index = pc.get_index()
    vector_ids = [f"{tid}_audio" for tid in track_ids]
    result = index.fetch(ids=vector_ids, namespace=pc.NAMESPACE_AUDIO)
    # Pinecone 5.x FetchResponse has a .vectors attr; dict .get() is a fallback
    vectors = getattr(result, "vectors", None) or result.get("vectors", {})
    already = {vid.replace("_audio", "") for vid in vectors}
    return [tid for tid in track_ids if tid not in already]


def get_audio_features_safe(track_ids: list[str], genre: str) -> dict[str, dict]:
    """
    Try Spotify audio features; fall back to jittered genre defaults on any 403.
    Returns track_id → feature dict for every requested ID.
    """
    global _audio_features_unavailable

    features_map: dict[str, dict] = {}

    if _SPOTIFY_AVAILABLE and not _audio_features_unavailable:
        try:
            raw = _sp.get_audio_features(track_ids)
            for f in raw:
                if f and f.get("id"):
                    features_map[f["id"]] = f
        except Exception as e:
            msg = str(e)
            if "403" in msg or "forbidden" in msg.lower() or "premium" in msg.lower():
                print(
                    "  ⚠  Spotify audio-features endpoint returned 403. "
                    "Switching to genre-based defaults for all remaining tracks."
                )
                _audio_features_unavailable = True
            else:
                print(f"  ⚠  audio-features error (non-fatal): {e}")

    # Fill missing entries with per-track jittered genre defaults
    defaults = GENRE_FEATURE_DEFAULTS.get(genre, GENRE_FEATURE_DEFAULTS["pop"])
    for tid in track_ids:
        if tid not in features_map:
            jittered = {
                k: round(v + random.uniform(-0.06, 0.06), 4) if isinstance(v, float) else v
                for k, v in defaults.items()
            }
            jittered["id"] = tid
            features_map[tid] = jittered

    return features_map


def fetch_tracks_for_artist(artist: str) -> list[dict]:
    """Search iTunes by artist name; return up to TRACKS_PER_ARTIST results."""
    try:
        tracks = itunes.search_tracks_by_artist(artist, limit=TRACKS_PER_ARTIST)
    except Exception as e:
        print(f"    ⚠ iTunes search failed for '{artist}': {e}")
        return []

    # Keep only tracks where the searched artist appears in the credit
    artist_lower = artist.lower().replace(" and ", " & ")
    def matches(t: dict) -> bool:
        name = t.get("artistName", "").lower().replace(" and ", " & ")
        return artist_lower in name or name in artist_lower

    filtered = [t for t in tracks if matches(t)]
    # If filtering is too aggressive (e.g. classical performers), keep a few anyway
    return filtered if filtered else tracks[:5]


def process_track(track: dict, genre: str, features: dict, catalog_tier: str) -> dict | None:
    """Convert an iTunes search result + audio features into our song schema."""
    track_id = str(track.get("trackId", ""))
    if not track_id:
        return None

    artist_name = track.get("artistName", "")
    track_name  = track.get("trackName",  "")
    release_year = int((track.get("releaseDate") or "0000")[:4])

    return {
        "song_id":        track_id,
        "title":          track_name,
        "artist":         artist_name,
        "album":          track.get("collectionName", ""),
        "year":           release_year,
        "genre":          genre,
        "duration":       itunes.format_duration(track.get("trackTimeMillis", 0)),
        "preview_url":    track.get("previewUrl"),
        "image_url":      itunes.high_res_artwork(track.get("artworkUrl100")),
        "spotify_url":    itunes.external_url(artist_name, track_name),
        "catalog_tier":   catalog_tier,
        "audio_features": features,
    }


def build_pinecone_vectors(
    song_data: dict,
    audio_emb_vec: list[float],
    lyrics_emb_vec: list[float] | None,
) -> list[dict]:
    # Pinecone metadata values must be scalars (string/number/bool) or list[str].
    # Nested dicts are rejected with a 400. We flatten audio features as top-level
    # keys with an "af_" prefix — this also enables future filtering on them.
    # None values are also rejected — replace with empty string for optional fields.
    base_meta = {
        k: (v if v is not None else "")
        for k, v in song_data.items()
        if k != "audio_features"
    }
    # artist_lower enables case-insensitive metadata filtering in search_by_artist
    base_meta["artist_lower"] = song_data.get("artist", "").strip().lower()
    af = song_data["audio_features"]
    base_meta["af_energy"]           = float(af.get("energy",           0))
    base_meta["af_tempo"]            = float(af.get("tempo",            0))
    base_meta["af_valence"]          = float(af.get("valence",          0))
    base_meta["af_danceability"]     = float(af.get("danceability",     0))
    base_meta["af_acousticness"]     = float(af.get("acousticness",     0))
    base_meta["af_instrumentalness"] = float(af.get("instrumentalness", 0))
    base_meta["af_speechiness"]      = float(af.get("speechiness",      0))
    base_meta["af_loudness"]         = float(af.get("loudness",         0))
    base_meta["af_key"]              = int(af.get("key",  0))
    base_meta["af_mode"]             = int(af.get("mode", 0))
    base_meta["af_liveness"]         = float(af.get("liveness",         0))

    vectors = [{
        "id":       f"{song_data['song_id']}_audio",
        "values":   audio_emb_vec,
        "metadata": {**base_meta, "namespace": "audio"},
    }]
    if lyrics_emb_vec:
        vectors.append({
            "id":       f"{song_data['song_id']}_lyrics",
            "values":   lyrics_emb_vec,
            "metadata": {**base_meta, "namespace": "lyrics"},
        })
    return vectors


# ── Main seeding loop ─────────────────────────────────────────────────────────

def seed():
    print("🎵 MelodyMatch Seeding Script  (iTunes + Genius + Voyage AI + Pinecone)")
    print("=" * 60)

    print("Connecting to Pinecone...")
    pc.get_index()
    print(f"  ✓ Index '{pc.INDEX_NAME}' ready\n")

    print("Validating Genius API token…")
    try:
        gc.validate_token()
        print("  ✓ Genius token is valid\n")
    except RuntimeError as e:
        print(f"\n  ✗ {e}\n")
        sys.exit(1)

    if _SPOTIFY_AVAILABLE:
        print("  ℹ  Spotify client loaded — will attempt audio-features lookup.")
    else:
        print("  ℹ  Spotify client unavailable — using genre-based feature defaults.")
    print()

    total_seeded  = 0
    total_skipped = 0

    for genre, (artists, catalog_tier) in GENRE_ARTISTS.items():
        print(f"📂 Genre: {genre.upper()}  ({len(artists)} artists · tier={catalog_tier})")

        # ── Collect unique tracks across all artists ──────────────────────────
        seen_ids:   set[str]        = set()
        all_tracks: dict[str, dict] = {}  # track_id → iTunes result dict

        for artist in artists:
            raw = fetch_tracks_for_artist(artist)
            for t in raw:
                tid = str(t.get("trackId", ""))
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    all_tracks[tid] = t
            time.sleep(0.4)  # stay well inside iTunes rate limit

        print(f"  Found {len(all_tracks)} unique tracks via iTunes search")

        # ── Batch-check what's already in Pinecone ────────────────────────────
        all_ids  = list(all_tracks.keys())
        new_ids  = get_unindexed_ids(all_ids)
        skipped  = len(all_ids) - len(new_ids)
        total_skipped += skipped

        if not new_ids:
            print(f"  ✓ All tracks already indexed\n")
            continue

        new_tracks = [all_tracks[tid] for tid in new_ids]
        print(f"  {len(new_tracks)} new tracks to index ({skipped} already exist)")

        # ── Fetch audio features (Spotify if available, else genre defaults) ──
        features_map = get_audio_features_safe(new_ids, genre)

        # ── Build song dicts ──────────────────────────────────────────────────
        song_entries: list[dict] = []
        for track in new_tracks:
            tid      = str(track.get("trackId", ""))
            features = features_map.get(tid, {})
            sd       = process_track(track, genre, features, catalog_tier)
            if sd:
                song_entries.append(sd)

        print(f"  Processing {len(song_entries)} valid tracks...")

        # ── Audio description embeddings ──────────────────────────────────────
        audio_descriptions = [
            emb.generate_audio_description(
                sd["audio_features"], sd["title"], sd["artist"], sd["genre"]
            )
            for sd in song_entries
        ]
        audio_embeddings: list[list[float]] = []
        for i in range(0, len(audio_descriptions), BATCH_EMBED_SIZE):
            batch = audio_descriptions[i : i + BATCH_EMBED_SIZE]
            audio_embeddings.extend(emb.embed_texts(batch))
            time.sleep(0.1)

        # ── Lyrics fetch + embed ──────────────────────────────────────────────
        # Genius rate-limits aggressively on the free tier. With verbose=False
        # the library returns None silently instead of raising, so we must
        # slow down and log explicitly so we can see what's working.
        lyrics_texts:   list[str] = []
        lyrics_indices: list[int] = []
        lyrics_found = 0
        print(f"  Fetching lyrics for {len(song_entries)} tracks (this takes a while)…")
        for idx, sd in enumerate(song_entries):
            lyrics = gc.get_lyrics(sd["title"], sd["artist"])
            if lyrics and len(lyrics) > 100:
                lyrics_texts.append(lyrics[:3000])
                lyrics_indices.append(idx)
                lyrics_found += 1
            # Progress dot every 10 songs
            if (idx + 1) % 10 == 0:
                print(f"    {idx + 1}/{len(song_entries)} checked, {lyrics_found} lyrics found so far")
            time.sleep(1.5)   # Genius free tier: ~1 req/s is the safe limit
        print(f"  Lyrics fetched: {lyrics_found}/{len(song_entries)} songs had lyrics")

        lyrics_embeddings_raw: list[list[float]] = []
        for i in range(0, len(lyrics_texts), BATCH_EMBED_SIZE):
            batch = lyrics_texts[i : i + BATCH_EMBED_SIZE]
            lyrics_embeddings_raw.extend(emb.embed_texts(batch))
            time.sleep(0.1)

        lyrics_emb_map = {
            lyrics_indices[i]: lyrics_embeddings_raw[i]
            for i in range(len(lyrics_indices))
        }

        # ── Build and upsert Pinecone vectors ─────────────────────────────────
        audio_vecs:  list[dict] = []
        lyrics_vecs: list[dict] = []
        for idx, (sd, audio_emb_vec) in enumerate(zip(song_entries, audio_embeddings)):
            lyrics_emb_vec = lyrics_emb_map.get(idx)
            for v in build_pinecone_vectors(sd, audio_emb_vec, lyrics_emb_vec):
                if v["metadata"]["namespace"] == "audio":
                    audio_vecs.append(v)
                else:
                    lyrics_vecs.append(v)

        for i in range(0, len(audio_vecs), UPSERT_BATCH_SIZE):
            pc.upsert_vectors(audio_vecs[i : i + UPSERT_BATCH_SIZE], pc.NAMESPACE_AUDIO)
            time.sleep(0.5)   # avoid overwhelming the connection pool
        for i in range(0, len(lyrics_vecs), UPSERT_BATCH_SIZE):
            pc.upsert_vectors(lyrics_vecs[i : i + UPSERT_BATCH_SIZE], pc.NAMESPACE_LYRICS)
            time.sleep(0.5)

        total_seeded += len(song_entries)
        print(f"  ✓ Indexed {len(song_entries)} songs ({len(lyrics_vecs)} with lyrics)\n")

    print("=" * 60)
    print(f"✅ Done: {total_seeded} new songs indexed, {total_skipped} already existed")


if __name__ == "__main__":
    seed()
