"""
Hybrid Schema Linker — RRF 融合 Keyword + Embedding 两路召回。

设计原则：
- 零侵入：不修改 SchemaLinker 和 TableEmbedder
- 向后兼容：link() 输出格式 100% 兼容 SchemaLinker.link()
- 容错降级：Embedding 不可用时自动退化为纯 Keyword

融合策略：Reciprocal Rank Fusion (RRF)
  score = Σ 1 / (60 + rank_i)

用法：
    from app.services.text2sql.hybrid_linker import HybridSchemaLinker

    linker = HybridSchemaLinker()
    await linker.warmup()       # 预热 Embedding 索引（失败不阻塞）
    linked = await linker.link("万华化学去年营收多少")
    prompt = linker.build_schema_prompt(linked)  # 复用 SchemaLinker 的输出格式
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schema_linking import SchemaLinker
from .embedding import TableEmbedder

logger = logging.getLogger("text2sql.hybrid_linker")

# ═══════════════════════════════════════════════════════
#  RRF 常数
# ═══════════════════════════════════════════════════════

RRF_K = 60

# schema.json 路径
_SCHEMA_PATH = Path(__file__).parent / "schema.json"


# ═══════════════════════════════════════════════════════
#  统一数据结构
# ═══════════════════════════════════════════════════════

@dataclass
class MatchedColumn:
    """统一列匹配结果，归一化来自 Keyword / Alias / Embedding 三路的命中信息"""
    column_name: str
    column_type: str = "NUMERIC"
    column_desc: str = ""
    source: Set[str] = field(default_factory=set)   # {"keyword", "alias", "embedding"}
    keyword_score: float = 0.0
    embedding_score: float = 0.0
    combined_score: float = 0.0


@dataclass
class Candidate:
    """统一候选表，承载融合前的中间结果"""
    table_name: str
    table_desc: str = ""
    columns: List[MatchedColumn] = field(default_factory=list)
    final_score: float = 0.0      # RRF 融合后的最终得分
    keyword_rank: int = 0          # 在 Keyword 路中的排名（1-indexed；0 = 未出现）
    embedding_rank: int = 0        # 在 Embedding 路中的排名（1-indexed；0 = 未出现）

    @property
    def source_labels(self) -> List[str]:
        """人类可读的来源标签"""
        labels = []
        if self.keyword_rank > 0:
            labels.append(f"keyword(#{self.keyword_rank})")
        if self.embedding_rank > 0:
            labels.append(f"embedding(#{self.embedding_rank})")
        return labels


# ═══════════════════════════════════════════════════════
#  HybridSchemaLinker
# ═══════════════════════════════════════════════════════

class HybridSchemaLinker:
    """
    混合 Schema 链接器。

    流程:
      Question → [Keyword Retrieval + Embedding Retrieval] → Normalize → RRF → Output

    内部持有：
      - SchemaLinker（不改）— keyword + alias + metadata 匹配
      - TableEmbedder（不改）— SentenceTransformer + Redis 语义匹配
    """

    def __init__(self):
        self._keyword_linker = SchemaLinker()
        self._table_embedder = TableEmbedder()
        self._embedding_available = False
        self._schema = self._load_schema()

        # 表定义快速索引：table_name → {"description": ..., "columns": [...]}
        self._table_defs: Dict[str, Dict] = {}
        self._build_table_index()

    # ── schema 属性（兼容 main.py health endpoint 的 len(linker.schema)）──

    @property
    def schema(self) -> Dict:
        return self._schema

    # ── 初始化辅助 ────────────────────────────────────

    def _load_schema(self) -> Dict:
        """加载 schema.json"""
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_table_index(self) -> None:
        """构建表名 → 表定义 的快速查找索引"""
        for table_name, table_def in self._schema.items():
            self._table_defs[table_name] = {
                "description": table_def.get("description", ""),
                "columns": table_def.get("columns", []),
            }

    # ── Warmup ────────────────────────────────────────

    async def warmup(self) -> None:
        """
        预热 Embedding 索引。

        流程：
          1. 将 schema.json 中 5 张表 → TableEmbedder.index_tables()
          2. 嵌入向量写入 Redis
          3. 成功后标记 _embedding_available = True

        失败策略：
          - 捕获所有异常
          - 记录 WARNING 日志
          - _embedding_available 保持 False
          - 后续请求自动降级为纯 Keyword 模式
        """
        try:
            logger.info("HybridSchemaLinker: warming up embedding index...")
            await self._table_embedder.index_tables(self._schema)
            self._embedding_available = True
            logger.info(
                f"HybridSchemaLinker: embedding ready "
                f"({len(self._schema)} tables indexed)"
            )
        except Exception as e:
            self._embedding_available = False
            logger.warning(
                f"HybridSchemaLinker: embedding warmup failed — "
                f"{type(e).__name__}: {e}. "
                f"Falling back to keyword-only mode."
            )

    # ═══════════════════════════════════════════════════
    #  公共 API
    # ═══════════════════════════════════════════════════

    async def link(
        self,
        query: str,
        allowed_tables: Optional[List[str]] = None,
        top_k: int = 3,
    ) -> Dict:
        """
        执行 Hybrid Schema Linking。

        签名和返回值格式与 SchemaLinker.link() 100% 兼容。
        唯一差异：本方法是 async。

        Args:
            query: 用户自然语言问题
            allowed_tables: 表白名单
            top_k: 最终返回几张表

        Returns:
            {"tables": [...], "relationships": [...]}
            格式与 SchemaLinker._build_result() 完全一致
        """
        # ── Phase 1: 并行召回 ──────────────────────────
        # Keyword 路（同步）：SchemaLinker.link()
        keyword_candidates = self._run_keyword(query, allowed_tables)

        # Embedding 路（异步）：TableEmbedder.search_relevant_tables()
        embedding_candidates = await self._run_embedding(query, top_k=5)

        logger.debug(
            f"HybridSchemaLinker.phase1: "
            f"keyword={len(keyword_candidates)} tables, "
            f"embedding={len(embedding_candidates)} tables"
        )

        # ── Phase 2: RRF 融合 ──────────────────────────
        fused = self._fuse_rrf(keyword_candidates, embedding_candidates)

        # ── Phase 3: 列级增强 ──────────────────────────
        # Keyword 未命中的表（纯 embedding 侧召回）补充兜底列
        for cand in fused:
            self._enhance_columns(cand)

        # ── Phase 4: 截断 top_k ────────────────────────
        fused.sort(key=lambda c: c.final_score, reverse=True)
        top_candidates = fused[:top_k]

        # ── 兜底逻辑 ────────────────────────────────────
        if not top_candidates:
            # RRF 融合结果为空 → 退化到纯 Keyword
            logger.warning(
                "HybridSchemaLinker: RRF returned empty result, "
                "falling back to keyword-only"
            )
            top_candidates = keyword_candidates[:top_k]

        if not top_candidates:
            # Keyword 也为空 → 返回允许表列表中前 top_k 张表
            candidate_table_names = (
                [t for t in allowed_tables if t in self._schema]
                if allowed_tables
                else list(self._schema.keys())
            )
            top_candidates = [
                self._make_fallback_candidate(t)
                for t in candidate_table_names[:top_k]
            ]
            logger.warning(
                f"HybridSchemaLinker: complete fallback, "
                f"returning {len(top_candidates)} tables"
            )

        # ── 日志 ────────────────────────────────────────
        table_summary = ", ".join(
            f"{c.table_name}(rrf={c.final_score:.4f}, {c.source_labels})"
            for c in top_candidates
        )
        logger.info(
            f"HybridSchemaLinker: query='{query[:60]}...' → "
            f"[{table_summary}] "
            f"embedding={'on' if self._embedding_available else 'off'}"
        )

        return self._to_schema_linker_format(top_candidates)

    def build_schema_prompt(self, linked: Dict) -> str:
        """
        复用 SchemaLinker 的 prompt 构建逻辑。

        因为 HybridSchemaLinker.link() 的输出与 SchemaLinker.link() 100% 兼容，
        所以直接委托给 SchemaLinker.build_schema_prompt()。
        """
        return self._keyword_linker.build_schema_prompt(linked)

    # ═══════════════════════════════════════════════════
    #  Keyword 召回（不改 SchemaLinker）
    # ═══════════════════════════════════════════════════

    def _run_keyword(
        self,
        query: str,
        allowed_tables: Optional[List[str]],
    ) -> List[Candidate]:
        """
        调用 SchemaLinker.link() → 归一化为 Candidate 列表。

        参数 top_k=10 确保获取所有候选表（当前只有 5 张表），
        给 RRF 提供完整的 Keyword 排名信息。
        """
        result = self._keyword_linker.link(
            query, allowed_tables=allowed_tables, top_k=10
        )

        candidates = []
        for table in result.get("tables", []):
            table_name = table["name"]
            match_score = table.get("match_score", 0)
            columns = self._extract_columns_from_keyword_result(
                query, table_name, table.get("column_details", []), match_score
            )
            candidates.append(Candidate(
                table_name=table_name,
                table_desc=table.get("description", ""),
                columns=columns,
                final_score=float(match_score),
            ))

        return candidates

    def _extract_columns_from_keyword_result(
        self,
        query: str,
        table_name: str,
        column_details: List[Dict],
        match_score: float,
    ) -> List[MatchedColumn]:
        """
        从 SchemaLinker 返回的 column_details 中提取并判定每列的匹配来源。

        判定逻辑：
          - 列名本身出现在 query 中         → source += "keyword"
          - 列的任一 alias 出现在 query 中   → source += "alias"
          - 两者都不满足但 match_score > 0   → 该列是 SchemaLinker 的兜底列
        """
        columns = []
        query_lower = query.lower()

        for col_detail in column_details:
            col_name = col_detail.get("name", "")
            col_def = self._find_column_def(table_name, col_name)
            aliases = col_def.get("alias", []) if col_def else []

            source: Set[str] = set()

            # 列名字面匹配
            if col_name.lower() in query_lower:
                source.add("keyword")

            # 别名匹配
            for alias in aliases:
                if alias.lower() in query_lower or alias in query:
                    source.add("alias")
                    break

            columns.append(MatchedColumn(
                column_name=col_name,
                column_type=col_detail.get("type", "NUMERIC"),
                column_desc=col_detail.get("description", ""),
                source=source,
                keyword_score=1.0 if source else 0.0,
            ))

        return columns

    # ═══════════════════════════════════════════════════
    #  Embedding 召回（不改 TableEmbedder）
    # ═══════════════════════════════════════════════════

    async def _run_embedding(self, query: str, top_k: int = 5) -> List[Candidate]:
        """
        调用 TableEmbedder.search_relevant_tables() → 归一化为 Candidate 列表。

        容错：
          - Embedding 未 warmup → 返回空列表
          - Redis 不可用 → 捕获异常，返回空列表
          - 模型加载失败 → 捕获异常，返回空列表
        """
        if not self._embedding_available:
            return []

        try:
            results = await self._table_embedder.search_relevant_tables(
                query, top_k=top_k
            )
        except Exception as e:
            logger.warning(
                f"HybridSchemaLinker: embedding search error — "
                f"{type(e).__name__}: {e}"
            )
            return []

        candidates = []
        for table_name, similarity in results:
            table_def = self._table_defs.get(table_name)
            candidates.append(Candidate(
                table_name=table_name,
                table_desc=table_def["description"] if table_def else "",
                columns=[],   # 列信息留空，由 _enhance_columns 兜底填充
                final_score=similarity,
            ))

        return candidates

    # ═══════════════════════════════════════════════════
    #  RRF 融合
    # ═══════════════════════════════════════════════════

    def _fuse_rrf(
        self,
        keyword_cands: List[Candidate],
        embedding_cands: List[Candidate],
    ) -> List[Candidate]:
        """
        Reciprocal Rank Fusion。

        公式: RRF_score = Σ 1 / (60 + rank_i)

        步骤：
          1. 构建两路排名索引 (table_name → rank)
          2. 合并所有唯一表名
          3. 对每张表计算 RRF 分数
          4. 填充 keyword_rank / embedding_rank 元信息
          5. 按 RRF 分数降序排序

        如果某张表只出现在一条路径中，另一条路径的排名贡献为 0。
        """
        # Step 1: 计算两路排名
        kw_ranks: Dict[str, int] = {}
        for rank, cand in enumerate(keyword_cands, start=1):
            kw_ranks[cand.table_name] = rank

        emb_ranks: Dict[str, int] = {}
        for rank, cand in enumerate(embedding_cands, start=1):
            emb_ranks[cand.table_name] = rank

        # Step 2: 合并所有唯一表名（保留 Keyword 侧的 Candidate 优先）
        all_tables: Dict[str, Candidate] = {}
        for cand in keyword_cands:
            all_tables[cand.table_name] = cand
        for cand in embedding_cands:
            if cand.table_name not in all_tables:
                all_tables[cand.table_name] = cand

        # Step 3 & 4: 计算 RRF 分数 & 填充元信息
        fused = []
        for table_name, cand in all_tables.items():
            kw_rank = kw_ranks.get(table_name, 0)
            emb_rank = emb_ranks.get(table_name, 0)

            rrf_score = 0.0
            if kw_rank > 0:
                rrf_score += 1.0 / (RRF_K + kw_rank)
            if emb_rank > 0:
                rrf_score += 1.0 / (RRF_K + emb_rank)

            cand.final_score = rrf_score
            cand.keyword_rank = kw_rank
            cand.embedding_rank = emb_rank
            fused.append(cand)

        # Step 5: 按 RRF 降序
        fused.sort(key=lambda c: c.final_score, reverse=True)

        logger.debug(
            f"HybridSchemaLinker.RRF: "
            f"{len(keyword_cands)} keyword + {len(embedding_cands)} embedding "
            f"→ {len(fused)} fused"
        )

        return fused

    # ═══════════════════════════════════════════════════
    #  列级增强
    # ═══════════════════════════════════════════════════

    def _enhance_columns(self, cand: Candidate) -> None:
        """
        为候选表补充列级信息。

        - Keyword 侧匹配到的列：补充缺失的 column_type / column_desc
        - 纯 Embedding 侧召回的列（columns 为空）：兜底取前 8 列
        """
        table_def = self._table_defs.get(cand.table_name)
        if not table_def:
            return

        schema_columns = table_def.get("columns", [])

        if cand.columns:
            # 有列信息 → 补充 type / desc
            for col in cand.columns:
                col_def = self._find_column_def_from_list(
                    schema_columns, col.column_name
                )
                if col_def:
                    col.column_type = col_def.get("type", "NUMERIC")
                    col.column_desc = col_def.get("description", "")
        else:
            # 纯 Embedding 侧匹配 → 兜底取前 8 列
            for col_def in schema_columns[:8]:
                cand.columns.append(MatchedColumn(
                    column_name=col_def["name"],
                    column_type=col_def.get("type", "NUMERIC"),
                    column_desc=col_def.get("description", ""),
                    source={"embedding"},
                ))

    # ═══════════════════════════════════════════════════
    #  格式转换 → 100% 兼容 SchemaLinker._build_result()
    # ═══════════════════════════════════════════════════

    def _to_schema_linker_format(self, candidates: List[Candidate]) -> Dict:
        """
        将 Candidate 列表转换为 SchemaLinker.link() 兼容的 Dict。

        输出结构与 SchemaLinker._build_result() 完全一致：
          {
            "tables": [
              {
                "name": str,
                "description": str,
                "columns": [str, ...],          # 列名列表
                "column_details": [              # 列详情
                  {"name": str, "type": str, "description": str}
                ],
                "primary_keys": [str, ...],
                "match_score": float
              }
            ],
            "relationships": [...]
          }
        """
        linked_tables = []
        table_names: Set[str] = set()

        for cand in candidates:
            table_names.add(cand.table_name)

            column_names = [c.column_name for c in cand.columns]
            column_details = [
                {
                    "name": c.column_name,
                    "type": c.column_type,
                    "description": c.column_desc,
                }
                for c in cand.columns
            ]

            # 主键推断（与 SchemaLinker 一致：stock_code / company_name）
            primary_keys = [
                c.column_name
                for c in cand.columns
                if c.column_name in ("stock_code", "company_name")
            ]

            # RRF 分数缩放到合理范围（权重信息保留）
            match_score = round(cand.final_score * 100, 2)

            linked_tables.append({
                "name": cand.table_name,
                "description": cand.table_desc,
                "columns": column_names,
                "column_details": column_details,
                "primary_keys": primary_keys,
                "match_score": match_score,
            })

        # 跨表关系检测（与 SchemaLinker._build_result() 一致）
        relationships = []
        if "financials" in table_names and "stock_basic" in table_names:
            relationships.append({
                "from_table": "financials",
                "from_column": "stock_code",
                "to_table": "stock_basic",
                "to_column": "stock_code",
            })
        if "balance_sheet" in table_names and "stock_basic" in table_names:
            relationships.append({
                "from_table": "balance_sheet",
                "from_column": "stock_code",
                "to_table": "stock_basic",
                "to_column": "stock_code",
            })

        return {"tables": linked_tables, "relationships": relationships}

    # ═══════════════════════════════════════════════════
    #  内部工具方法
    # ═══════════════════════════════════════════════════

    def _find_column_def(
        self, table_name: str, column_name: str
    ) -> Optional[Dict]:
        """在 schema.json 中查找某张表的某列定义"""
        table_def = self._schema.get(table_name, {})
        for col in table_def.get("columns", []):
            if col["name"] == column_name:
                return col
        return None

    @staticmethod
    def _find_column_def_from_list(
        columns: List[Dict], column_name: str
    ) -> Optional[Dict]:
        """在列定义列表中查找指定列"""
        for col in columns:
            if col["name"] == column_name:
                return col
        return None

    def _make_fallback_candidate(self, table_name: str) -> Candidate:
        """
        创建兜底 Candidate。

        当 Keyword 和 Embedding 两路都无结果时使用。
        返回该表前 8 列，全部标记为 keyword 来源。
        """
        table_def = self._table_defs.get(table_name, {})
        columns = []
        for col_def in table_def.get("columns", [])[:8]:
            columns.append(MatchedColumn(
                column_name=col_def["name"],
                column_type=col_def.get("type", "NUMERIC"),
                column_desc=col_def.get("description", ""),
                source={"keyword"},
            ))
        return Candidate(
            table_name=table_name,
            table_desc=table_def.get("description", ""),
            columns=columns,
            final_score=0.0,
        )
