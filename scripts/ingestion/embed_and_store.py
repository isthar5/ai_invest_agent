import os
import re
import time
import hashlib
from typing import Iterable

from qdrant_client import QdrantClient, models
from fastembed import TextEmbedding, SparseTextEmbedding
from app.retrieval.dedup import deduplicate_indices
from app.config.stock_pool import CHEMICAL_STOCK_POOL


def get_client() -> QdrantClient:
    host = os.getenv("QDRANT_HOST", "127.0.0.1")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    return QdrantClient(host=host, port=port)


def get_collection_name() -> str:
    return os.getenv("COLLECTION_NAME", "invest_data")


def create_collection(client: QdrantClient, collection_name: str, recreate: bool = False) -> None:
    vectors_config = {
        "dense_vector": models.VectorParams(size=384, distance=models.Distance.COSINE),
    }
    sparse_vectors_config = {
        "bm25": models.SparseVectorParams(index=models.SparseIndexParams()),
    }
    if recreate:
        client.recreate_collection(
            collection_name=collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )
        return
    exists = client.collection_exists(collection_name)
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )


def parse_year(source: str) -> int | None:
    m = re.search(r"(20\d{2})", source)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def parse_company(source: str, title: str, sample_text: str) -> tuple[str | None, str | None]:
    combined = f"{source}\n{title}\n{sample_text}"
    for code, info in CHEMICAL_STOCK_POOL.items():
        name = info.get("name")
        if not name:
            continue
        if name in combined or code in combined:
            ticker = f"{code}.SH" if str(code).startswith("6") else f"{code}.SZ"
            return name, ticker
    return None, None


def make_point_id(source: str, chunk_index: int, text: str) -> str:
    h = hashlib.sha1()
    h.update(source.encode("utf-8", errors="ignore"))
    h.update(b"\n")
    h.update(str(chunk_index).encode("utf-8"))
    h.update(b"\n")
    h.update(text.encode("utf-8", errors="ignore"))
    return h.hexdigest()


def iter_batches(items: list, batch_size: int) -> Iterable[list]:
    if batch_size <= 0:
        yield items
        return
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def store_chunks(
    client: QdrantClient,
    collection_name: str,
    chunks: list,
    source: str,
    title: str = "",
    doc_id: str | None = None,
    doc_type: str | None = None,
    timestamp: str | None = None,
    batch_size: int = 64,
    skip_existing: bool = True,
) -> int:
    dense_model = TextEmbedding("BAAI/bge-small-zh-v1.5")
    sparse_model = SparseTextEmbedding("Qdrant/bm25")
    dedup = os.getenv("INGEST_DEDUP", "1") == "1"
    dedup_threshold = float(os.getenv("INGEST_DEDUP_THRESHOLD", "0.92"))

    if doc_id is None:
        doc_id = os.path.splitext(os.path.basename(source))[0]
    if not title:
        title = doc_id
    if timestamp is None:
        try:
            ts = os.path.getmtime(source) if os.path.exists(source) else time.time()
        except Exception:
            ts = time.time()
        timestamp = str(int(ts))

    def _to_text_and_meta(items: list):
        texts = []
        metas = []
        for it in items:
            if isinstance(it, dict):
                text = it.get("text") or ""
                meta = dict(it)
                meta.pop("text", None)
                texts.append(text)
                metas.append(meta)
            else:
                texts.append(str(it))
                metas.append({})
        return texts, metas

    year = parse_year(source)
    texts, metas = _to_text_and_meta(chunks)
    sample_text = next((t for t in texts if t.strip()), "")
    company, ticker = parse_company(source, title, sample_text)

    stored = 0
    dense_embeddings = list(dense_model.embed(texts))
    sparse_embeddings = list(sparse_model.embed(texts))

    if dedup and texts:
        idx = deduplicate_indices([e.tolist() for e in dense_embeddings], threshold=dedup_threshold)
        texts = [texts[i] for i in idx]
        metas = [metas[i] for i in idx]
        dense_embeddings = [dense_embeddings[i] for i in idx]
        sparse_embeddings = [sparse_embeddings[i] for i in idx]

    point_ids = [make_point_id(source, i, text) for i, text in enumerate(texts)]
    existing_ids = set()
    if skip_existing and point_ids:
        for batch in iter_batches(point_ids, 256):
            try:
                records = client.retrieve(collection_name=collection_name, ids=batch, with_payload=False, with_vectors=False)
                for r in records:
                    existing_ids.add(str(r.id))
            except Exception:
                existing_ids = set()
                break

    points: list[models.PointStruct] = []
    for i, text in enumerate(texts):
        pid = point_ids[i]
        if skip_existing and pid in existing_ids:
            continue
        dense_vec = dense_embeddings[i].tolist()
        sparse_obj = sparse_embeddings[i].as_object()
        sparse_vec = models.SparseVector(
            indices=sparse_obj["indices"].tolist(),
            values=sparse_obj["values"].tolist(),
        )

        payload = {
            "doc_id": doc_id,
            "text": text,
            "title": title,
            "source": source,
            "timestamp": timestamp,
        }
        if year is not None:
            payload["year"] = year
        if doc_type is not None:
            payload["type"] = doc_type
        if company is not None:
            payload["company"] = company
        if ticker is not None:
            payload["ticker"] = ticker
        page_num = metas[i].get("page_num")
        page_range = metas[i].get("page_range")
        if page_num is not None:
            payload["page_num"] = int(page_num)
        if page_range is not None:
            payload["page_range"] = page_range
        payload["metadata"] = {
            "page_num": payload.get("page_num"),
            "page_range": payload.get("page_range"),
            "source": source,
            "ticker": payload.get("ticker"),
            "company": payload.get("company"),
            "year": payload.get("year"),
            "type": payload.get("type"),
        }

        points.append(
            models.PointStruct(
                id=pid,
                vector={"dense_vector": dense_vec, "bm25": sparse_vec},
                payload=payload,
            )
        )

        if len(points) >= batch_size:
            client.upsert(collection_name=collection_name, points=points)
            stored += len(points)
            points = []

    if points:
        client.upsert(collection_name=collection_name, points=points)
        stored += len(points)

    return stored
