import os
import asyncio
from qdrant_client import QdrantClient
from qdrant_client.http.models import SparseVector
from app.retrieval.embedder import embed
from app.config.settings import settings
from typing import List, Tuple, Dict, Any

client = QdrantClient(
    host=settings.QDRANT_HOST,
    port=settings.QDRANT_PORT,
)

COLLECTION_NAME = settings.COLLECTION_NAME



def normalize(scores: List[float]) -> List[float]:
    if not scores:
        return []
    min_s = min(scores)
    max_s = max(scores)
    denom = (max_s - min_s) + 1e-6
    return [(s - min_s) / denom for s in scores]


def dynamic_weights(query: str) -> Tuple[float, float]:
    # Query-aware Fusion：短query偏BM25，长query偏Dense
    if len(query) < 10:
        return (0.3, 0.7)
    else:
        return (0.7, 0.3)


def hybrid_fusion(dense_hits, sparse_hits, method="rrf", weights=(0.5, 0.5), k=60) -> List[Tuple[str, Dict[str, Any]]]:
    """
    支持 RRF 和 Weighted Sum 两种融合方式
    weights: (dense_weight, sparse_weight)
    """
    scores = {}

    if method == "rrf":
        def update(hits, source):
            for rank, hit in enumerate(hits):
                doc_id = hit.id
                score = 1 / (k + rank + 1)
                if doc_id not in scores:
                    scores[doc_id] = {
                        "score": 0,
                        "dense_rank": None,
                        "sparse_rank": None,
                        "dense_score": None,
                        "sparse_score": None,
                        "metadata": hit.payload
                    }
                scores[doc_id]["score"] += score
                if source == "dense":
                    scores[doc_id]["dense_rank"] = rank + 1
                    scores[doc_id]["dense_score"] = hit.score
                else:
                    scores[doc_id]["sparse_rank"] = rank + 1
                    scores[doc_id]["sparse_score"] = hit.score
        update(dense_hits, "dense")
        update(sparse_hits, "sparse")
    
    elif method == "weighted":
        # 动态权重（若未指定）
        dw, sw = weights
        # 先收集原始分数用于归一化
        dense_scores_raw = [hit.score for hit in dense_hits]
        sparse_scores_raw = [hit.score for hit in sparse_hits]
        dense_scores_norm = normalize(dense_scores_raw)
        sparse_scores_norm = normalize(sparse_scores_raw)

        def update(hits, source, weight, norm_scores):
            for rank, hit in enumerate(hits):
                doc_id = hit.id
                norm_score = norm_scores[rank] if rank < len(norm_scores) else 0.0
                weighted = norm_score * weight
                if doc_id not in scores:
                    scores[doc_id] = {
                        "score": 0,
                        "dense_rank": None,
                        "sparse_rank": None,
                        "dense_score": None,
                        "sparse_score": None,
                        "metadata": hit.payload
                    }
                scores[doc_id]["score"] += weighted
                if source == "dense":
                    scores[doc_id]["dense_rank"] = rank + 1
                    scores[doc_id]["dense_score"] = hit.score
                else:
                    scores[doc_id]["sparse_rank"] = rank + 1
                    scores[doc_id]["sparse_score"] = hit.score

        update(dense_hits, "dense", dw, dense_scores_norm)
        update(sparse_hits, "sparse", sw, sparse_scores_norm)

    return sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)


async def hybrid_search(query, limit=20, method="rrf", weights=None, query_filter=None):
    dense_vec, sparse_vec = await embed(query)

    dense_task = asyncio.to_thread(
        client.query_points,
        collection_name=COLLECTION_NAME,
        query=dense_vec,
        using="dense_vector",
        query_filter=query_filter,
        limit=limit,
        with_payload=True
    )

    sparse_query = SparseVector(**sparse_vec) if isinstance(sparse_vec, dict) else sparse_vec
    sparse_task = asyncio.to_thread(
        client.query_points,
        collection_name=COLLECTION_NAME,
        query=sparse_query,
        using="bm25",
        query_filter=query_filter,
        limit=limit,
        with_payload=True
    )

    dense_resp, sparse_resp = await asyncio.gather(dense_task, sparse_task)
    dense_hits = dense_resp.points
    sparse_hits = sparse_resp.points

    # 动态融合：若是 weighted 且未显式给定权重，则根据 query 动态分配
    if method == "weighted" and weights is None:
        weights = dynamic_weights(query)

    fused = hybrid_fusion(dense_hits, sparse_hits, method=method, weights=weights)

    return fused, dense_hits, sparse_hits


async def smart_search(query, limit_primary=10, limit_backoff=30, threshold_k=3):
    fused, _, _ = await hybrid_search(query, limit=limit_primary, method="rrf")
    if len(fused) < threshold_k:
        fused, _, _ = await hybrid_search(query, limit=limit_backoff, method="weighted")
    return fused
