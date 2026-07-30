import os
import time
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

NAMESPACE_AUDIO = "audio"
NAMESPACE_LYRICS = "lyrics"
EMBEDDING_DIM = 1024
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "melodymatch")

_pc: Pinecone | None = None
_index = None


def get_client() -> Pinecone:
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    return _pc


def get_index():
    global _index
    if _index is None:
        pc = get_client()
        existing = [idx.name for idx in pc.list_indexes()]
        if INDEX_NAME not in existing:
            pc.create_index(
                name=INDEX_NAME,
                dimension=EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        _index = pc.Index(INDEX_NAME)
    return _index


def _reset_index() -> None:
    """Force the index handle to be re-acquired on next call (after a connection drop)."""
    global _index
    _index = None


def upsert_vectors(vectors: list[dict], namespace: str, max_retries: int = 4) -> None:
    """
    Upsert vectors with exponential-backoff retry on transient connection errors.

    Pinecone serverless occasionally drops TCP connections (errno 54 "Connection
    reset by peer") during large writes. Retrying with a fresh connection handle
    always resolves it.
    """
    for attempt in range(max_retries):
        try:
            index = get_index()
            index.upsert(vectors=vectors, namespace=namespace)
            return
        except Exception as e:
            msg = str(e).lower()
            transient = (
                "connection" in msg
                or "reset" in msg
                or "protocol" in msg
                or "timeout" in msg
                or "503" in msg
                or "502" in msg
            )
            if transient and attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)   # 5 s, 10 s, 20 s
                print(
                    f"\n    ⚠  Pinecone connection dropped — waiting {wait}s "
                    f"then retrying (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(wait)
                _reset_index()  # force a fresh connection on next get_index()
            else:
                raise


def query_vectors(
    vector: list[float],
    namespace: str,
    top_k: int = 8,
    filter: dict | None = None,
) -> list[dict]:
    index = get_index()
    result = index.query(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
        filter=filter,
    )
    # Pinecone 5.x returns a QueryResponse object with a .matches attribute.
    # Older versions returned a plain dict — support both to be safe.
    matches = getattr(result, "matches", None)
    if matches is None:
        matches = result.get("matches", [])
    # Convert ScoredVector objects to plain dicts if needed
    output = []
    for m in matches:
        if isinstance(m, dict):
            output.append(m)
        else:
            output.append({
                "id":       m.id,
                "score":    m.score,
                "metadata": m.metadata or {},
            })
    return output
