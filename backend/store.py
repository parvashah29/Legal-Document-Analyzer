"""Vector store + embeddings. Remote Qdrant if reachable, otherwise local on-disk Qdrant."""
import logging
import threading
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams,
)

import config

log = logging.getLogger("legal.store")

_lock = threading.Lock()
_client = None
_backend_info = {"backend": "uninitialized", "detail": ""}
_embedder = None


def _connect():
    if config.QDRANT_URL and config.QDRANT_API_KEY and not config.QDRANT_FORCE_LOCAL:
        try:
            c = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=8)
            c.get_collections()
            _backend_info.update(backend="qdrant-cloud", detail="remote Qdrant")
            return c
        except Exception as e:  # noqa: BLE001
            log.warning("Remote Qdrant unreachable (%s); using local on-disk store.", type(e).__name__)
    if config.QDRANT_LOCAL_PATH == ":memory:":
        _backend_info.update(backend="qdrant-memory", detail="in-memory (non-persistent)")
        return QdrantClient(":memory:")
    config.QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)
    _backend_info.update(backend="qdrant-local-disk", detail=f"on-disk at {config.QDRANT_LOCAL_PATH}")
    return QdrantClient(path=str(config.QDRANT_LOCAL_PATH))


def get_client() -> QdrantClient:
    global _client
    with _lock:
        if _client is None:
            _client = _connect()
            _ensure_collection(_client)
        return _client


def _ensure_collection(c: QdrantClient):
    existing = [x.name for x in c.get_collections().collections]
    if config.QDRANT_COLLECTION not in existing:
        c.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBED_DIM, distance=Distance.COSINE),
        )
    if _backend_info["backend"] == "qdrant-cloud":  # payload indexes only matter on a server
        try:
            c.create_payload_index(config.QDRANT_COLLECTION, "doc_id", "keyword")
        except Exception:  # noqa: BLE001
            pass


def backend_info() -> dict:
    return dict(_backend_info)


def get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name=config.EMBED_MODEL_NAME)
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    return [list(map(float, v)) for v in get_embedder().embed(texts)]


def _doc_filter(doc_id: str) -> Filter:
    return Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])


def add_chunks(doc_id: str, filename: str, chunks: list[str]) -> None:
    vectors = embed(chunks)
    points = [
        PointStruct(
            id=str(uuid.uuid4()), vector=v,
            payload={"doc_id": doc_id, "text": c, "chunk_index": i, "filename": filename},
        )
        for i, (c, v) in enumerate(zip(chunks, vectors))
    ]
    get_client().upsert(collection_name=config.QDRANT_COLLECTION, points=points)


def search(doc_id: str, question: str, limit: int = 5) -> list[dict]:
    """Top-k chunks of ONE document only (filter on doc_id)."""
    qv = embed([question])[0]
    res = get_client().query_points(
        collection_name=config.QDRANT_COLLECTION, query=qv, limit=limit,
        query_filter=_doc_filter(doc_id), with_payload=True,
    )
    return [
        {"text": p.payload["text"], "chunk_index": p.payload["chunk_index"], "score": round(float(p.score), 3)}
        for p in res.points
    ]


def get_chunks(doc_id: str) -> list[dict]:
    """All chunks of a document in order (paginated scroll)."""
    out, offset = [], None
    while True:
        pts, offset = get_client().scroll(
            collection_name=config.QDRANT_COLLECTION, scroll_filter=_doc_filter(doc_id),
            limit=256, offset=offset, with_payload=True,
        )
        out += [p.payload for p in pts]
        if offset is None:
            break
    return sorted(out, key=lambda p: p["chunk_index"])


def delete_document(doc_id: str) -> None:
    get_client().delete(
        collection_name=config.QDRANT_COLLECTION,
        points_selector=FilterSelector(filter=_doc_filter(doc_id)),
    )
