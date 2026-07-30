import asyncio
import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from dotenv import load_dotenv

import job_queue
import search as search_module
from models import AgentEvent, SongResult

load_dotenv()

SYSTEM_PROMPT = """You are MelodyMatch, an expert music discovery AI. Users describe the kind of music they're looking for — by mood, melody style, lyrical theme, tempo, instrument, emotional feeling, or reference to a specific song or artist — and you find real songs that match.

You have five tools available:

Artist-specific tool (use this FIRST when the user asks for songs BY a specific artist):
- search_by_artist: finds songs by a named artist using exact metadata lookup. Use this whenever the user asks for songs "by [artist]", "from [artist]", "[artist] songs", or any phrasing that clearly identifies a specific artist they want music FROM (not just inspired by).

Mood/style search tools (use these to find songs with similar qualities):
- search_by_audio_mood: finds songs by sonic qualities (energy, tempo, mood, acousticness, danceability, instrumentation)
- search_by_lyrics_theme: finds songs by lyrical content, themes, emotions in the words
- search_combined: uses both, weighted by how much the user cares about sound vs. lyrics

Background indexing tool (use this to grow the database):
- queue_artist_index: queues an artist for background indexing to improve future searches. Call this whenever the user's query mentions a specific artist by name. This runs silently in the background and does NOT affect response time.

Workflow:
1. Analyze the user's query
2. If the user wants songs BY a specific artist:
   a. Call queue_artist_index first (returns instantly, ensures the artist is indexed)
   b. Call search_by_artist with that artist's name
   c. If search_by_artist returns 0 songs: tell the user the artist isn't in the database yet, that you've queued them for background indexing, and that results will be available within a few minutes. Do NOT fall back to a mood search — be explicit about the empty result.
   d. If search_by_artist returns songs: return those songs with match_reason explaining the connection to the user's request
3. If the user wants songs SIMILAR TO an artist or describes a mood/style → call the appropriate mood/style tool(s) (and still call queue_artist_index if an artist is mentioned)
4. After getting results, select the best 5 songs and write a 1-2 sentence explanation for each saying WHY it matches the user's request
5. Return your final answer as a call to the `return_results` tool

Query crafting tips:
- For audio searches: write a full sentence covering energy, tempo (include a BPM estimate if implied), mood, tonality (major/bright vs minor/dark), vocals vs instrumental, danceability, and production style (acoustic/organic vs electronic/produced, loud vs intimate). Example: "mellow laid-back music at a slow 70 BPM ballad pace, melancholic wistful mood, minor key dark tonality, melodic sung vocals, organic acoustic instrumentation, soft intimate production"
- For lyrics searches: describe the themes, emotions, imagery, and narrative in a few phrases, e.g. "songs about losing someone you love, grief, memories of a past relationship, learning to move on"
- Translate the user's words generously: "chill" → mellow laid-back low energy; "bangers" → explosive high-intensity danceable; "rainy day" → melancholic quiet acoustic. Expand vague requests into concrete sonic and emotional qualities.
- Be specific and descriptive — the embedding model understands nuance, and richer queries produce better-separated match scores

Always explain your reasoning in the match_reason field for each song. Reference specific qualities from the user's request."""

TOOLS: list[dict] = [
    {
        "name": "search_by_artist",
        "description": "Search for songs by a specific named artist using exact metadata lookup. Use this when the user asks for songs BY an artist (e.g. 'songs by Her\\'s', 'give me some Taylor Swift songs', 'play me some Beatles'). This returns real songs from that artist in the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {
                    "type": "string",
                    "description": "The exact artist name to search for, e.g. 'Her\\'s', 'Taylor Swift', 'The Beatles'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 10)",
                    "default": 10,
                },
            },
            "required": ["artist_name"],
        },
    },
    {
        "name": "search_by_audio_mood",
        "description": "Search for songs by their sonic and musical qualities: tempo, energy, mood, acousticness, danceability, instrumentation. Use for requests about how a song SOUNDS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of the desired sonic qualities, e.g. 'slow melancholic acoustic piano ballad with soft vocals'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 8)",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_by_lyrics_theme",
        "description": "Search for songs by lyrical content, themes, meaning, and emotions expressed in the words. Use for requests about what a song is ABOUT.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of the desired lyrical themes, e.g. 'songs about heartbreak and moving on from a relationship'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 8)",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_combined",
        "description": "Search using both audio qualities and lyrical themes simultaneously, with configurable weighting. Use when the user cares about both sound and meaning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_query": {
                    "type": "string",
                    "description": "Natural language description of desired sonic qualities",
                },
                "lyrics_query": {
                    "type": "string",
                    "description": "Natural language description of desired lyrical themes",
                },
                "audio_weight": {
                    "type": "number",
                    "description": "Weight for audio similarity, 0.0–1.0. Lyrics weight = 1 - audio_weight. Default 0.5.",
                    "default": 0.5,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 8)",
                    "default": 8,
                },
            },
            "required": ["audio_query", "lyrics_query"],
        },
    },
    {
        "name": "queue_artist_index",
        "description": "Queue an artist for background indexing to grow the song database. Call this whenever the user mentions a specific artist by name. It returns immediately and runs in the background without affecting response time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist_name": {
                    "type": "string",
                    "description": "The exact artist name as mentioned by the user, e.g. 'Taylor Swift', 'Kendrick Lamar', 'The Beatles'",
                },
            },
            "required": ["artist_name"],
        },
    },
    {
        "name": "return_results",
        "description": "Return the final ranked song results to the user. Always call this as the last step.",
        "input_schema": {
            "type": "object",
            "properties": {
                "songs": {
                    "type": "array",
                    "description": "Ordered list of song IDs to return (most relevant first)",
                    "items": {"type": "string"},
                },
                "explanation": {
                    "type": "string",
                    "description": "1-2 sentence overall explanation of the search strategy and what these songs have in common",
                },
                "match_reasons": {
                    "type": "object",
                    "description": "Map of song_id to a 1-sentence explanation of why that specific song matches",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["songs", "explanation", "match_reasons"],
        },
    },
]


def _serialize_song(song: SongResult) -> dict:
    return {
        "song_id": song.song_id,
        "title": song.title,
        "artist": song.artist,
        "album": song.album,
        "year": song.year,
        "genre": song.genre,
        "duration": song.duration,
        "similarity": song.similarity,
        "preview_url": song.preview_url,
        "image_url": song.image_url,
        "spotify_url": song.spotify_url,
    }


async def run_streaming(
    query: str, search_type: str, restrict_to_popular: bool = False
) -> AsyncGenerator[str, None]:
    # AsyncAnthropic is required here — the sync client blocks the event loop
    # inside an async generator, which causes Uvicorn to drop the SSE connection
    # mid-stream (ERR_INCOMPLETE_CHUNKED_ENCODING).
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_message = f"Search type preference: {search_type}\n\nUser query: {query}"
    messages: list[dict] = [{"role": "user", "content": user_message}]

    song_pool: dict[str, SongResult] = {}

    def emit(event: AgentEvent) -> str:
        return f"data: {event.model_dump_json()}\n\n"

    loop = asyncio.get_event_loop()

    max_iterations = 6
    for _ in range(max_iterations):
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Emit any text blocks as thinking events
        for block in response.content:
            if block.type == "text" and block.text.strip():
                yield emit(AgentEvent(type="thinking", text=block.text.strip()))

        # If no tool use, we're done unexpectedly
        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            if tool_name == "return_results":
                # Final step — assemble the response
                song_ids = tool_input.get("songs", [])
                explanation = tool_input.get("explanation", "")
                match_reasons: dict[str, str] = tool_input.get("match_reasons", {})

                ordered = []
                for sid in song_ids:
                    if sid in song_pool:
                        song = song_pool[sid].model_copy()
                        song.match_reason = match_reasons.get(sid)
                        ordered.append(song)

                # Fill with any remaining pool songs if Claude omitted some
                if not ordered and song_pool:
                    ordered = list(song_pool.values())[:5]

                yield emit(AgentEvent(
                    type="result",
                    songs=ordered,
                    explanation=explanation,
                ))
                return

            # ── queue_artist_index: fire-and-forget, no executor needed ──────────
            if tool_name == "queue_artist_index":
                artist_name = tool_input.get("artist_name", "").strip()
                if artist_name:
                    queued = job_queue.enqueue(artist_name)
                    status = "queued for background indexing" if queued else "already indexed"
                else:
                    status = "no artist name provided"
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     f"Artist '{artist_name}': {status}.",
                })
                continue   # skip the search-tool execution block below

            # Emit tool call event
            query_text = (
                tool_input.get("artist_name")
                or tool_input.get("query")
                or tool_input.get("audio_query", "")
            )
            yield emit(AgentEvent(type="tool_call", tool=tool_name, query=query_text))

            # Execute the tool — search functions are synchronous (Voyage AI +
            # Pinecone), so run them in a thread to avoid blocking the event loop.
            tool_output: Any = None
            try:
                if tool_name == "search_by_artist":
                    requested_artist = tool_input["artist_name"]
                    songs = await loop.run_in_executor(
                        None,
                        lambda: search_module.search_by_artist(
                            artist_name=requested_artist,
                            top_k=tool_input.get("top_k", 10),
                            restrict_to_popular=restrict_to_popular,
                        ),
                    )
                    for s in songs:
                        song_pool[s.song_id] = s
                    if songs:
                        tool_output = [_serialize_song(s) for s in songs]
                    else:
                        # Give Claude an explicit signal so it informs the user
                        tool_output = {
                            "found": 0,
                            "artist": requested_artist,
                            "message": (
                                f"No songs by '{requested_artist}' found in the database. "
                                "The artist has been queued for background indexing — "
                                "songs will be available within a few minutes."
                            ),
                        }

                elif tool_name == "search_by_audio_mood":
                    songs = await loop.run_in_executor(
                        None,
                        lambda: search_module.search_by_audio_mood(
                            query=tool_input["query"],
                            top_k=tool_input.get("top_k", 8),
                            restrict_to_popular=restrict_to_popular,
                        ),
                    )
                    for s in songs:
                        song_pool[s.song_id] = s
                    tool_output = [_serialize_song(s) for s in songs]

                elif tool_name == "search_by_lyrics_theme":
                    songs = await loop.run_in_executor(
                        None,
                        lambda: search_module.search_by_lyrics_theme(
                            query=tool_input["query"],
                            top_k=tool_input.get("top_k", 8),
                            restrict_to_popular=restrict_to_popular,
                        ),
                    )
                    for s in songs:
                        song_pool[s.song_id] = s
                    tool_output = [_serialize_song(s) for s in songs]

                elif tool_name == "search_combined":
                    songs = await loop.run_in_executor(
                        None,
                        lambda: search_module.search_combined(
                            audio_query=tool_input["audio_query"],
                            lyrics_query=tool_input["lyrics_query"],
                            audio_weight=tool_input.get("audio_weight", 0.5),
                            top_k=tool_input.get("top_k", 8),
                            restrict_to_popular=restrict_to_popular,
                        ),
                    )
                    for s in songs:
                        song_pool[s.song_id] = s
                    tool_output = [_serialize_song(s) for s in songs]

                yield emit(AgentEvent(type="tool_result", count=len(tool_output)))

            except Exception as exc:
                tool_output = {"error": str(exc)}
                yield emit(AgentEvent(type="error", text=f"Tool {tool_name} failed: {exc}"))

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(tool_output),
            })

        # Append assistant response and tool results to message history
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        if response.stop_reason == "end_turn":
            break

    # Fallback if agent never called return_results
    if song_pool:
        fallback = list(song_pool.values())[:5]
        yield emit(AgentEvent(
            type="result",
            songs=fallback,
            explanation="Here are the closest matches I found for your query.",
        ))
    else:
        yield emit(AgentEvent(
            type="error",
            text="No results found. Try rephrasing your query.",
        ))
