# app/scripts/ingest_to_qdrant.py
import os
import sys
import asyncio
import hashlib
from typing import List, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.ingestion.loader import MarkdownLoader
from app.retrieval.embedder import embed
from app.config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 配置 ====================
COLLECTION_NAME = settings.COLLECTION_NAME
QDRANT_HOST = settings.QDRANT_HOST
QDRANT_PORT = settings.QDRANT_PORT
MARKDOWN_DIR = str(settings.MARKDOWN_DIR)
BATCH_SIZE = 50  # 批量入库大小


class QdrantIngestor:
    """Qdrant 入库器"""
    
    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.loader = MarkdownLoader()
        self.collection_name = COLLECTION_NAME
    
    def ensure_collection(self):
        """确保集合存在，不存在则创建"""
        if self.client.collection_exists(self.collection_name):
            logger.info(f"集合 {self.collection_name} 已存在")
            return
        
        logger.info(f"创建集合 {self.collection_name}")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense_vector": qmodels.VectorParams(
                    size=512,  # bge-small-zh-v1.5 的维度
                    distance=qmodels.Distance.COSINE
                )
            },
            sparse_vectors_config={
                "bm25": qmodels.SparseVectorParams(
                    index=qmodels.SparseIndexParams()
                )
            }
        )
        logger.info("集合创建成功")
    
    def generate_point_id(self, text: str, source: str, chunk_idx: int) -> int:
        """生成唯一的点 ID"""
        unique_str = f"{source}_{chunk_idx}_{text[:100]}"
        return int(hashlib.md5(unique_str.encode()).hexdigest()[:16], 16)
    
    async def ingest_markdown_file(self, file_path: str) -> List[Dict]:
        """入库单个 Markdown 文件"""
        logger.info(f"处理文件: {file_path}")
        
        # 1. 加载并切分文档
        chunks = self.loader.load(file_path)
        logger.info(f"  切分为 {len(chunks)} 个块")
        
        points = []
        file_name = os.path.basename(file_path)
        
        for idx, chunk in enumerate(chunks):
            try:
                # 提取文本内容
                if hasattr(chunk, 'content'):
                    text = chunk['content']
                    metadata = chunk.get('metadata', {})
                elif hasattr(chunk, 'page_content'):
                    text = chunk.page_content
                    metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
                elif isinstance(chunk, dict):
                    text = chunk.get('content', str(chunk))
                    metadata = chunk.get('metadata', {})
                else:
                    text = str(chunk)
                    metadata = {}
                
                if not text or len(text.strip()) < 20:
                    continue
                
                # 2. 向量化
                dense, sparse = await embed(text)
                
                # 3. 生成 ID
                point_id = self.generate_point_id(text, file_name, idx)
                
                # 4. 构建 payload
                payload = {
                    "text": text[:3000],  # 限制长度，避免过大
                    "source": file_name,
                    "chunk_idx": idx,
                    "company": metadata.get('company', ''),
                    "year": metadata.get('year', ''),
                    "section": metadata.get('section', ''),
                    "has_table": metadata.get('has_table', False),
                }
                
                points.append({
                    "id": point_id,
                    "vector": {
                        "dense_vector": dense,
                        "bm25": sparse
                    },
                    "payload": payload
                })
                
            except Exception as e:
                logger.error(f"  处理块 {idx} 失败: {e}")
                continue
        
        return points
    
    async def ingest_directory(self, directory: str):
        """入库整个目录"""
        self.ensure_collection()
        
        # 获取所有 markdown 文件
        md_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(".md"):
                    md_files.append(os.path.join(root, file))
        
        logger.info(f"找到 {len(md_files)} 个 Markdown 文件")
        
        total_points = 0
        all_points = []
        
        for file_path in md_files:
            points = await self.ingest_markdown_file(file_path)
            all_points.extend(points)
            total_points += len(points)
            
            # 批量入库
            if len(all_points) >= BATCH_SIZE:
                await self._upsert_batch(all_points)
                logger.info(f"  已入库 {total_points} 个块")
                all_points = []
        
        # 入库剩余的
        if all_points:
            await self._upsert_batch(all_points)
        
        logger.info(f"✅ 入库完成！共 {total_points} 个块")
        
        # 打印集合信息
        collection_info = self.client.get_collection(self.collection_name)
        logger.info(f"集合点数: {collection_info.points_count}")
    
    async def _upsert_batch(self, points: List[Dict]):
        """批量入库"""
        qdrant_points = []
        for p in points:
            qdrant_points.append(
                qmodels.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"]
                )
            )
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=qdrant_points
        )
    
    def delete_collection(self):
        """删除集合（谨慎使用）"""
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
            logger.info(f"已删除集合 {self.collection_name}")
    
    def get_collection_stats(self):
        """获取集合统计信息"""
        if not self.client.collection_exists(self.collection_name):
            return {"error": "集合不存在"}
        
        info = self.client.get_collection(self.collection_name)
        return {
            "name": self.collection_name,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": "ready"
        }


# ==================== 独立函数接口 ====================
async def ingest_all_markdowns(md_dir: str = None):
    """入库所有 Markdown 文件"""
    if md_dir is None:
        md_dir = MARKDOWN_DIR
    
    ingestor = QdrantIngestor()
    await ingestor.ingest_directory(md_dir)
    return ingestor.get_collection_stats()


async def ingest_single_file(file_path: str):
    """入库单个文件"""
    ingestor = QdrantIngestor()
    ingestor.ensure_collection()
    points = await ingestor.ingest_markdown_file(file_path)
    await ingestor._upsert_batch(points)
    logger.info(f"✅ 文件 {file_path} 入库完成，共 {len(points)} 个块")
    return len(points)


def check_collection():
    """检查集合状态"""
    ingestor = QdrantIngestor()
    stats = ingestor.get_collection_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return stats


# ==================== 主入口 ====================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Qdrant 入库脚本")
    parser.add_argument("--action", choices=["ingest", "check", "delete"], default="ingest",
                        help="操作类型: ingest(入库), check(检查), delete(删除)")
    parser.add_argument("--file", type=str, help="单个文件路径")
    parser.add_argument("--dir", type=str, default=MARKDOWN_DIR, help="目录路径")
    
    args = parser.parse_args()
    
    if args.action == "ingest":
        if args.file:
            asyncio.run(ingest_single_file(args.file))
        else:
            asyncio.run(ingest_all_markdowns(args.dir))
    
    elif args.action == "check":
        check_collection()
    
    elif args.action == "delete":
        ingestor = QdrantIngestor()
        ingestor.delete_collection()
