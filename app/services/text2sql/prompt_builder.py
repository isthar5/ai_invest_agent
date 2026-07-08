"""
Prompt Builder — 为 Text2SQL 构建 LLM Prompt（Registry 薄封装）。

两种模式：
1. 首次生成：注入完整的 Schema 上下文
2. 错误修正：注入上一次 SQL + 数据库报错信息

v2.0 变更：
- 模板从 PromptRegistry 读取（不再硬编码）
- 对外接口 100% 保持兼容
- Registry 不可用时自动使用内置 Fallback

用法：
    from app.services.text2sql.prompt_builder import PromptBuilder

    builder = PromptBuilder()
    prompt = builder.build_first(question="万华去年营收", schema_prompt="...")
    prompt = builder.build_retry(question="万华去年营收", schema_prompt="...",
                                 last_sql="SELECT revenue FROM financials",
                                 error="Unknown column 'revenue'")
"""

import logging

from app.services.prompt.registry import get_registry

logger = logging.getLogger("text2sql.prompt_builder")


class PromptBuilder:
    """SQL 生成 Prompt 构造器（Registry 薄封装）"""

    def __init__(self, current_year: int = 2026):
        self.current_year = current_year
        self._registry = get_registry()

    def build_first(self, question: str, schema_prompt: str) -> str:
        """
        构建首次 SQL 生成的 Prompt。

        Args:
            question: 用户自然语言问题
            schema_prompt: SchemaLinker.build_schema_prompt() 的输出

        Returns:
            完整的 LLM prompt 字符串
        """
        prompt = self._registry.render(
            "text2sql.first_attempt",
            schema_prompt=schema_prompt,
            question=question,
            current_year=self.current_year,
        )
        logger.info(
            f"PromptBuilder: first attempt, "
            f"question='{question[:50]}...', "
            f"prompt_length={len(prompt)}"
        )
        return prompt

    def build_retry(
        self,
        question: str,
        schema_prompt: str,
        last_sql: str,
        error: str,
    ) -> str:
        """
        构建 SQL 修正的 Prompt。

        Args:
            question: 用户原始问题
            schema_prompt: SchemaLinker.build_schema_prompt() 的输出
            last_sql: 上一次生成的 SQL
            error: 数据库返回的错误信息

        Returns:
            完整的修正 prompt 字符串
        """
        prompt = self._registry.render(
            "text2sql.retry",
            schema_prompt=schema_prompt,
            question=question,
            last_sql=last_sql,
            error=error,
        )
        logger.info(
            f"PromptBuilder: retry attempt, "
            f"error='{error[:80]}...', "
            f"prompt_length={len(prompt)}"
        )
        return prompt


def build_prompt(
    question: str,
    schema_prompt: str,
    error: str = None,
    last_sql: str = None,
) -> str:
    """
    便捷函数：根据是否有错误自动选择首次/重试模板。

    Args:
        question: 用户问题
        schema_prompt: Schema 描述文本
        error: 数据库错误信息（None 表示首次生成）
        last_sql: 上一次的 SQL（error 不为 None 时必填）

    Returns:
        LLM prompt 字符串
    """
    builder = PromptBuilder()
    if error and last_sql:
        return builder.build_retry(question, schema_prompt, last_sql, error)
    return builder.build_first(question, schema_prompt)
