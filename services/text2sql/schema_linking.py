import logging
from typing import List, Dict, Set

from .schema_cache import SchemaCache
from .embedding import TableEmbedder
from .alias_manager import AliasManager

logger = logging.getLogger("text2sql.schema_linking")


class SchemaLinker:
    """Schema Linking 核心模块"""

    def __init__(self):
        self.cache = SchemaCache()
        self.embedder = TableEmbedder()
        self.alias_mgr = AliasManager()

    async def _keyword_table_match(
        self, query: str, candidate_tables: List[str]
    ) -> List[str]:
        """基于关键词规则匹配表"""
        table_aliases = await self.alias_mgr.get_table_aliases()
        matched = set()
        query_lower = query.lower()

        for table in candidate_tables:
            table_lower = table.lower()
            if table_lower in query_lower:
                matched.add(table)
            for chinese, aliases in table_aliases.items():
                if chinese in query and table_lower in [a.lower() for a in aliases]:
                    matched.add(table)

        return list(matched)

    async def _filter_relevant_columns(
        self, table_name: str, schema: Dict, query: str
    ) -> List[str]:
        """筛选表中与查询相关的列"""
        column_aliases = await self.alias_mgr.get_column_aliases()
        relevant = set(schema.get("primary_keys", []))

        for fk in schema.get("foreign_keys", []):
            relevant.add(fk["column_name"])

        query_lower = query.lower()
        for col in schema.get("columns", []):
            col_name = col["name"].lower()
            if col_name in query_lower:
                relevant.add(col["name"])
                continue

            for chinese, aliases in column_aliases.items():
                if chinese in query and col_name in [a.lower() for a in aliases]:
                    relevant.add(col["name"])
                    break

        if len(relevant) <= 2:
            for col in schema.get("columns", [])[:8]:
                if not col["name"].startswith("_"):
                    relevant.add(col["name"])

        return list(relevant)

    async def link(
        self, query: str, allowed_tables: List[str], top_k: int = 3
    ) -> Dict:
        """
        执行 Schema Linking
        """
        logger.info(f"Schema Linking for query: {query[:50]}...")

        all_tables = await self.cache.get_tables()
        candidate_tables = [t for t in all_tables if t in allowed_tables]

        if not candidate_tables:
            logger.warning("No allowed tables found")
            return {"tables": [], "relationships": []}

        # 关键词匹配
        keyword_matched = await self._keyword_table_match(query, candidate_tables)

        # 向量召回
        vector_matched = []
        try:
            schemas = {}
            for t in candidate_tables:
                schemas[t] = await self.cache.get_table_schema(t)
            await self.embedder.index_tables(schemas)
            vector_results = await self.embedder.search_relevant_tables(query, top_k * 2)
            vector_matched = [t for t, _ in vector_results]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        # 合并结果（关键词优先）
        selected = list(dict.fromkeys(keyword_matched + vector_matched))[:top_k]
        if not selected:
            selected = candidate_tables[:top_k]

        logger.info(f"Selected tables: {selected}")

        # 构建链接结果
        linked_tables = []
        relationships = []

        for tname in selected:
            schema = await self.cache.get_table_schema(tname)
            cols = await self._filter_relevant_columns(tname, schema, query)
            sample = await self.cache.get_sample_rows(tname, 2)

            linked_tables.append({
                "name": tname,
                "columns": cols,
                "column_details": [
                    {
                        "name": c["name"],
                        "type": c["type"],
                        "nullable": c["nullable"]
                    }
                    for c in schema["columns"] if c["name"] in cols
                ],
                "primary_keys": schema.get("primary_keys", []),
                "sample_rows": sample
            })

            for fk in schema.get("foreign_keys", []):
                if fk["foreign_table_name"] in selected:
                    relationships.append({
                        "from_table": tname,
                        "from_column": fk["column_name"],
                        "to_table": fk["foreign_table_name"],
                        "to_column": fk["foreign_column_name"]
                    })

        return {"tables": linked_tables, "relationships": relationships}

    def build_schema_prompt(self, linked_schema: Dict) -> str:
        """将链接后的 Schema 转换为 LLM 友好的 Prompt"""
        if not linked_schema.get("tables"):
            return "No relevant tables found."

        prompt_parts = ["## Database Schema\n"]

        for table in linked_schema["tables"]:
            prompt_parts.append(f"\n### Table: {table['name']}\n")
            prompt_parts.append("Columns:")

            for col in table["column_details"]:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                prompt_parts.append(f"  - {col['name']} {col['type']} {nullable}")

            if table.get("primary_keys"):
                prompt_parts.append(f"Primary Key: {', '.join(table['primary_keys'])}")

            if table.get("sample_rows"):
                prompt_parts.append("Sample rows:")
                for row in table["sample_rows"]:
                    filtered = {
                        k: v for k, v in row.items()
                        if k in [c["name"] for c in table["column_details"]]
                    }
                    prompt_parts.append(f"  {filtered}")

        if linked_schema.get("relationships"):
            prompt_parts.append("\n### Relationships")
            for rel in linked_schema["relationships"]:
                prompt_parts.append(
                    f"  {rel['from_table']}.{rel['from_column']} -> "
                    f"{rel['to_table']}.{rel['to_column']}"
                )

        prompt_parts.append("\n## Instructions")
        prompt_parts.append("- Use only the tables and columns listed above.")
        prompt_parts.append("- Join tables using the relationships described.")
        prompt_parts.append("- Always include a LIMIT clause.")

        return "\n".join(prompt_parts)