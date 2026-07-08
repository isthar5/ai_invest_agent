"""
Schema Linking — 基于关键词 + 别名匹配的表/列召回。

设计原则：
- 5 张表、~50 列的场景，不需要向量召回
- 加载 schema.json，用 query 中的关键词匹配表描述和列别名
- 匹配到的列越多，表得分越高
- 支持允许表白名单过滤

用法：
    linker = SchemaLinker()
    linked = linker.link("万华去年营收多少", allowed_tables=["financials", "stock_basic"])
    prompt = linker.build_schema_prompt(linked)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger("text2sql.schema_linking")

# schema.json 与当前文件同目录
_SCHEMA_PATH = Path(__file__).parent / "schema.json"

# 全局缓存（模块级单例）
_schema_cache: Optional[Dict] = None


def _load_schema() -> Dict:
    """加载 schema.json（模块级缓存）"""
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        _schema_cache = json.load(f)
    logger.info(f"Loaded schema: {len(_schema_cache)} tables")
    return _schema_cache


class SchemaLinker:
    """Schema Linking 核心模块 — 纯关键词匹配，无向量依赖"""

    def __init__(self):
        self.schema = _load_schema()

    # ── 公开 API ──────────────────────────────────────

    def link(
        self,
        query: str,
        allowed_tables: Optional[List[str]] = None,
        top_k: int = 3,
    ) -> Dict:
        """
        执行 Schema Linking：根据 query 匹配相关表和列。

        Args:
            query: 用户自然语言问题
            allowed_tables: 允许的表名白名单，None 表示全部可用
            top_k: 最多返回几张表

        Returns:
            {"tables": [...], "relationships": [...]}
        """
        candidate_tables = self._get_candidate_tables(allowed_tables)
        if not candidate_tables:
            logger.warning("No candidate tables available")
            return {"tables": [], "relationships": []}

        # 给每张表打分（匹配到的列数）
        scored = []
        for table_name in candidate_tables:
            table_def = self.schema.get(table_name)
            if not table_def:
                continue
            matched_cols = self._match_columns(query, table_def)
            # 表描述也参与匹配（加分项）
            desc_bonus = self._match_description(query, table_def)
            score = len(matched_cols) + desc_bonus
            if score > 0 or len(candidate_tables) <= top_k:
                scored.append((table_name, score, matched_cols, table_def))

        # 按匹配分数降序，取 top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = scored[:top_k]

        # 如果一个都没匹配到，返回前 top_k 张表（兜底）
        if not selected or all(s[1] == 0 for s in selected):
            selected = [
                (t, 0, self._all_columns(self.schema.get(t, {})), self.schema.get(t, {}))
                for t in candidate_tables[:top_k]
            ]

        logger.info(
            f"Schema Linking: query='{query[:50]}...' → "
            f"tables={[s[0] for s in selected]}, scores={[s[1] for s in selected]}"
        )

        return self._build_result(selected)

    def build_schema_prompt(self, linked: Dict) -> str:
        """
        将链接后的 Schema 转换为 LLM 友好的 Prompt 文本。

        输出格式：
            ## 可用数据表

            ### financials — 上市公司利润表
            字段：
              - revenue  营业收入（主营业务收入）
              - net_profit  净利润（归母净利润）
              ...
        """
        tables = linked.get("tables", [])
        if not tables:
            return "No relevant tables found."

        parts = ["## 可用数据表\n"]

        for table in tables:
            tname = table["name"]
            tdesc = table.get("description", "")
            parts.append(f"### {tname} — {tdesc}\n")
            parts.append("字段：")

            for col in table.get("columns", []):
                col_name = col["name"]
                col_desc = col.get("description", "")
                aliases = col.get("alias", [])
                alias_str = "（" + "、".join(aliases[:3]) + "）" if aliases else ""
                parts.append(f"  - `{col_name}` {alias_str}{col_desc}")

            # 主键
            pks = table.get("primary_keys", [])
            if pks:
                parts.append(f"\n主键：{', '.join(pks)}")

            # 外键关系
            for rel in linked.get("relationships", []):
                if rel["from_table"] == tname:
                    parts.append(
                        f"关联：{rel['from_table']}.{rel['from_column']} "
                        f"→ {rel['to_table']}.{rel['to_column']}"
                    )

            parts.append("")  # 空行分隔

        parts.append("## 注意事项")
        parts.append("- 只允许 SELECT 查询")
        parts.append("- 必须包含 LIMIT 子句")
        parts.append("- 只能使用上面列出的表和字段")

        return "\n".join(parts)

    # ── 内部方法 ──────────────────────────────────────

    def _get_candidate_tables(self, allowed_tables: Optional[List[str]]) -> List[str]:
        """获取候选表列表"""
        all_tables = list(self.schema.keys())
        if allowed_tables:
            return [t for t in allowed_tables if t in self.schema]
        return all_tables

    def _match_columns(self, query: str, table_def: Dict) -> List[Dict]:
        """匹配 query 中提到的列，返回匹配到的列定义列表"""
        matched = []
        query_lower = query.lower()

        for col in table_def.get("columns", []):
            # 列名本身的匹配
            if col["name"].lower() in query_lower:
                matched.append(col)
                continue

            # 别名匹配
            for alias in col.get("alias", []):
                if alias.lower() in query_lower or alias in query:
                    matched.append(col)
                    break

        return matched

    def _match_description(self, query: str, table_def: Dict) -> float:
        """检查 query 是否提到了表描述中的关键词，返回加分"""
        desc = table_def.get("description", "")
        # 从描述中提取关键词，检查是否出现在 query 中
        keywords = ["利润表", "资产负债表", "现金流量表", "基本信息", "行业"]
        score = 0.0
        for kw in keywords:
            if kw in desc and kw in query:
                score += 0.5
        return score

    def _all_columns(self, table_def: Dict) -> List[Dict]:
        """返回表的所有列（兜底用）"""
        return table_def.get("columns", []) if table_def else []

    def _build_result(self, selected: List) -> Dict:
        """构建标准返回值"""
        linked_tables = []
        relationships = []

        for table_name, score, matched_cols, table_def in selected:
            # 如果没匹配到列，兜底展示前8列
            display_cols = matched_cols if matched_cols else table_def.get("columns", [])[:8]
            column_names = [c["name"] for c in display_cols]

            linked_tables.append({
                "name": table_name,
                "description": table_def.get("description", ""),
                "columns": [c["name"] for c in display_cols],
                "column_details": [
                    {
                        "name": c["name"],
                        "type": c.get("type", "NUMERIC"),
                        "description": c.get("description", ""),
                    }
                    for c in display_cols
                ],
                "primary_keys": [c["name"] for c in table_def.get("columns", [])
                                 if c["name"] in ("stock_code", "company_name")],
                "match_score": score,
            })

        # 跨表关系检测
        table_names = {t["name"] for t in linked_tables}
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
