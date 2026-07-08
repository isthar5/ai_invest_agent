"""
Embedding 模型模块 — 延迟加载 + 容错。

服务启动时不下载模型，首次调用时才加载。
加载失败返回 None 并记录日志，不阻塞启动。

导出:
  - embed(query) → async, 返回 (dense_vec, sparse_vec)  [hybrid.py 使用]
  - dense_model  → TextEmbedding 实例                  [rag/pipeline.py 使用]
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 延迟初始化
_dense_model: Optional[Any] = None
_sparse_model: Optional[Any] = None
_embedding_dim: int = 384  # bge-small-zh-v1.5


def _load_dense_model():
    """延迟加载 Dense embedding 模型。"""
    global _dense_model
    if _dense_model is None:
        try:
            from fastembed import TextEmbedding
            _dense_model = TextEmbedding("BAAI/bge-small-zh-v1.5")
            logger.info("Dense embedding model loaded (bge-small-zh-v1.5)")
        except Exception as e:
            logger.error(f"Failed to load dense embedding model: {e}")
            _dense_model = None
    return _dense_model


def _load_sparse_model():
    """延迟加载 Sparse/BM25 embedding 模型。"""
    global _sparse_model
    if _sparse_model is None:
        try:
            from fastembed import SparseTextEmbedding
            _sparse_model = SparseTextEmbedding("Qdrant/bm25")
            logger.info("Sparse/BM25 model loaded")
        except Exception as e:
            logger.error(f"Failed to load sparse model: {e}")
            _sparse_model = None
    return _sparse_model


def get_dense_model():
    """公开访问器 — 供 rag/pipeline.py 等需要直接调用 .query_embed() / .embed() 的模块。"""
    return _load_dense_model()


# 兼容旧代码: from app.retrieval.embedder import dense_model
# 通过 __getattr__ 实现模块级别的 lazy 属性访问
class _DenseModelProxy:
    """代理对象，使 dense_model.query_embed() / dense_model.embed() 延迟加载。"""

    def __getattr__(self, name: str):
        model = _load_dense_model()
        if model is None:
            raise RuntimeError("Dense embedding model not available")
        return getattr(model, name)


dense_model: Any = _DenseModelProxy()


async def embed(query: str) -> Tuple[Optional[List[float]], Optional[Dict[str, Any]]]:
    """
    生成文本的 Dense + Sparse 向量。

    Returns:
        (dense_vector, sparse_vector) — 若任一模型未加载，对应位置为 None。

    hybrid.py 调用: dense_vec, sparse_vec = await embed(query)
    """
    dense_model_obj = _load_dense_model()
    sparse_model_obj = _load_sparse_model()

    loop = asyncio.get_event_loop()

    # ── Dense ──
    if dense_model_obj is not None:
        try:
            dense = await loop.run_in_executor(
                None,
                lambda: next(dense_model_obj.query_embed(query)).tolist(),
            )
        except Exception as e:
            logger.error(f"Dense embedding error: {e}")
            dense = None
    else:
        logger.warning("Dense model unavailable, dense vector is None")
        dense = None

    # ── Sparse ──
    if sparse_model_obj is not None:
        try:
            sparse = await loop.run_in_executor(
                None,
                lambda: next(sparse_model_obj.query_embed(query)).as_object(),
            )
        except Exception as e:
            logger.error(f"Sparse embedding error: {e}")
            sparse = None
    else:
        logger.warning("Sparse model unavailable, sparse vector is None")
        sparse = None

    return dense, sparse
