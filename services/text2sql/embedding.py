import json
import logging
from typing import List, Tuple, Dict
import numpy as np
from sentence_transformers import SentenceTransformer

from .config import get_redis, EMBEDDING_MODEL, VECTOR_SIMILARITY_THRESHOLD

logger = logging.getLogger("text2sql.embedding")

# 全局模型单例
_embedder_model = None


def get_embedder_model():
    """获取向量模型单例"""
    global _embedder_model
    if _embedder_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedder_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder_model


class TableEmbedder:
    """表向量化及向量召回"""

    async def _get_redis(self):
        return await get_redis()

    def _build_table_description(self, table_name: str, schema: Dict) -> str:
        """构建表描述用于向量化"""
        cols = ", ".join([
            f"{c['name']}({c['type']})"
            for c in schema.get("columns", [])[:10]
        ])
        return f"表名: {table_name}, 包含字段: {cols}"

    async def index_tables(self, table_schemas: Dict[str, Dict]):
        """将表 Schema 向量化并存入 Redis"""
        redis = await self._get_redis()
        model = get_embedder_model()
        pipe = redis.pipeline()

        for table_name, schema in table_schemas.items():
            desc = self._build_table_description(table_name, schema)
            emb = model.encode(desc).tolist()

            # 存储向量
            pipe.set(f"embedding:table:{table_name}", json.dumps({
                "description": desc,
                "embedding": emb
            }))
            # 维护索引集合（替代 KEYS 命令）
            pipe.sadd("embedding:indexed_tables", table_name)

        await pipe.execute()
        logger.info(f"Indexed {len(table_schemas)} tables")

    async def search_relevant_tables(
        self, query: str, top_k: int = 3
    ) -> List[Tuple[str, float]]:
        """
        搜索与查询最相关的表
        使用 SET 维护索引列表，避免 KEYS 命令
        """
        redis = await self._get_redis()
        model = get_embedder_model()

        # 获取所有已索引的表名
        indexed_tables = await redis.smembers("embedding:indexed_tables")
        if not indexed_tables:
            logger.warning("No indexed tables found")
            return []

        q_emb = model.encode(query)
        results = []

        # 批量获取向量
        pipe = redis.pipeline()
        for table_name in indexed_tables:
            pipe.get(f"embedding:table:{table_name}")
        responses = await pipe.execute()

        for table_name, data_str in zip(indexed_tables, responses):
            if not data_str:
                continue
            data = json.loads(data_str)
            t_emb = np.array(data["embedding"])

            # 余弦相似度
            similarity = float(
                np.dot(q_emb, t_emb) /
                (np.linalg.norm(q_emb) * np.linalg.norm(t_emb) + 1e-8)
            )

            if similarity >= VECTOR_SIMILARITY_THRESHOLD:
                results.append((table_name, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def clear_index(self):
        """清空所有向量索引"""
        redis = await self._get_redis()
        indexed_tables = await redis.smembers("embedding:indexed_tables")
        if indexed_tables:
            pipe = redis.pipeline()
            for table_name in indexed_tables:
                pipe.delete(f"embedding:table:{table_name}")
            pipe.delete("embedding:indexed_tables")
            await pipe.execute()
        logger.info("Cleared all table embeddings")