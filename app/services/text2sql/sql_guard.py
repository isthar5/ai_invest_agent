"""
SQL Guard — 基于 sqlglot AST 解析的 SQL 安全校验。

校验规则：
1. 只允许 SELECT 语句
2. 表名必须在白名单中
3. 列名必须在白名单中（防止 LLM hallucination）
4. 必须包含 LIMIT 子句
5. 禁止危险函数调用（DROP, DELETE, INSERT, UPDATE, TRUNCATE 等）

用法：
    from app.services.text2sql.sql_guard import SQLGuard

    guard = SQLGuard(allowed_tables=["financials", "stock_basic"],
                     allowed_columns={"financials": ["revenue", "net_profit", ...]})
    try:
        guard.validate("SELECT revenue FROM financials LIMIT 10")
    except SecurityError as e:
        print(f"SQL 校验失败: {e}")
"""

import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger("text2sql.sql_guard")


class SecurityError(Exception):
    """SQL 安全校验异常"""
    pass


# 默认表白名单（从 schema.json 的 5 张表）
DEFAULT_TABLE_WHITELIST = {
    "financials",
    "balance_sheet",
    "cash_flow",
    "stock_basic",
    "industry_metrics",
}

# 禁止的 SQL 关键字/操作
FORBIDDEN_KEYWORDS = {
    "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "ALTER",
    "CREATE", "REPLACE", "MERGE", "GRANT", "REVOKE", "EXEC",
    "EXECUTE", "CALL", "COPY", "LOAD", "IMPORT",
}


class SQLGuard:
    """SQL 安全守卫"""

    def __init__(
        self,
        allowed_tables: Optional[Set[str]] = None,
        allowed_columns: Optional[Dict[str, Set[str]]] = None,
        max_limit: int = 1000,
        require_limit: bool = True,
    ):
        self.allowed_tables = allowed_tables or DEFAULT_TABLE_WHITELIST
        self.allowed_columns = allowed_columns or {}
        self.max_limit = max_limit
        self.require_limit = require_limit

    def validate(self, sql: str) -> str:
        """
        校验 SQL 语句，通过则返回（可能被规范化）的 SQL。

        Raises:
            SecurityError: 校验不通过
        """
        sql = sql.strip().rstrip(";").strip()

        # ── 1. 快速字符串检查（防御非 SELECT 语句） ──
        sql_upper = sql.upper()
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword in sql_upper:
                raise SecurityError(f"禁止的操作: {keyword}")

        # ── 2. AST 级别检查 ──
        try:
            import sqlglot
            tree = sqlglot.parse_one(sql)
        except Exception as e:
            raise SecurityError(f"SQL 语法解析失败: {e}")

        if tree is None:
            raise SecurityError("无法解析 SQL 语句")

        # 2a. 必须是 SELECT
        if tree.key.upper() != "SELECT":
            raise SecurityError(f"只允许 SELECT 查询，当前类型: {tree.key}")

        # 2b. 检查表名白名单
        tables = self._extract_tables(tree)
        for t in tables:
            if t not in self.allowed_tables:
                raise SecurityError(
                    f"表 '{t}' 不在白名单中。允许的表: {', '.join(sorted(self.allowed_tables))}"
                )

        # 2c. 检查列名白名单（仅当配置了列白名单时）
        if self.allowed_columns:
            columns = self._extract_columns(tree)
            self._check_columns(columns, tables)

        # 2d. 检查 LIMIT 子句
        if self.require_limit:
            limit_value = self._extract_limit(tree)
            if limit_value is None:
                raise SecurityError("SQL 必须包含 LIMIT 子句")
            if limit_value > self.max_limit:
                raise SecurityError(
                    f"LIMIT {limit_value} 超过最大允许值 {self.max_limit}"
                )

        logger.info(f"SQL Guard 校验通过: tables={tables}, limit={self._extract_limit(tree)}")
        return sql

    # ── AST 提取方法 ────────────────────────────────

    def _extract_tables(self, tree) -> Set[str]:
        """从 AST 中提取所有引用的表名"""
        tables = set()
        for node in tree.walk():
            if hasattr(node, "key") and node.key == "table":
                # 获取表名（去除可能的 schema 前缀和引号）
                name = node.name.strip('"').strip("'").strip("`")
                tables.add(name)
            # FROM 子句中的表
            if hasattr(node, "this") and hasattr(node, "key"):
                if node.key == "from" or node.key == "join":
                    if hasattr(node.this, "this"):
                        name = node.this.this
                        if isinstance(name, str):
                            tables.add(name.strip('"').strip("'").strip("`"))
        return tables

    def _extract_columns(self, tree) -> Set[str]:
        """从 AST 中提取所有引用的列名"""
        columns = set()
        for node in tree.walk():
            if hasattr(node, "key") and node.key == "column":
                name = node.name.strip('"').strip("'").strip("`")
                # 排除 * 通配符
                if name != "*":
                    columns.add(name)
            # 处理 table.column 形式
            if hasattr(node, "this") and hasattr(node, "args"):
                if hasattr(node, "key") and node.key == "column":
                    name = node.name.strip('"').strip("'").strip("`")
                    if name != "*":
                        columns.add(name)
        return columns

    def _extract_limit(self, tree) -> Optional[int]:
        """从 AST 中提取 LIMIT 值，没有则返回 None"""
        for node in tree.walk():
            if hasattr(node, "key") and node.key == "limit":
                # LIMIT 的值在 expression 或 this 中
                limit_node = getattr(node, "expression", None)
                if limit_node is not None:
                    return int(limit_node.name) if hasattr(limit_node, "name") else None
        return None

    def _check_columns(self, columns: Set[str], tables: Set[str]):
        """检查列名是否在任意一张引用表的白名单中"""
        # 构建全局合法列名集合
        all_allowed = set()
        for table in tables:
            if table in self.allowed_columns:
                all_allowed.update(self.allowed_columns[table])

        # 如果没有任何列白名单数据，跳过检查
        if not all_allowed:
            return

        for col in columns:
            if col not in all_allowed:
                raise SecurityError(
                    f"列 '{col}' 不在白名单中。"
                    f"可用列: {', '.join(sorted(all_allowed)[:20])}"
                )


def build_guard_from_schema(schema_path: str = None) -> SQLGuard:
    """
    从 schema.json 自动构建 SQLGuard 实例。

    提取所有表名和列名作为白名单。
    """
    import json
    from pathlib import Path

    if schema_path is None:
        schema_path = Path(__file__).parent / "schema.json"

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    allowed_tables = set(schema.keys())
    allowed_columns = {}
    for table_name, table_def in schema.items():
        col_names = {col["name"] for col in table_def.get("columns", [])}
        allowed_columns[table_name] = col_names

    logger.info(
        f"从 schema.json 构建 SQLGuard: "
        f"{len(allowed_tables)} 张表, "
        f"{sum(len(c) for c in allowed_columns.values())} 列"
    )
    return SQLGuard(allowed_tables=allowed_tables, allowed_columns=allowed_columns)
