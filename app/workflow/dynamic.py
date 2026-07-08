"""
M4 — Dynamic Task 与 Loop 执行器。

ForEachExecutor: 将列表中的每个元素展开为独立 task 执行。
LoopExecutor:     重复执行子 task 直到条件满足或达到最大迭代次数。

这两个 Executor 在 WorkflowRunner 层面展开，不修改 Runtime。

Usage (YAML):
    # ForEach
    analyze_each:
        executor: foreach
        config:
          items: "${tasks.screen.output.stocks}"
          item_var: stock
          task_template:
            executor: skill
            skill: financial_analysis
            config:
              stock: "${item.stock}"
              query: "${item.query}"

    # Loop
    retry_until_success:
        executor: loop
        config:
          max_iterations: 3
          condition: "${tasks.generate_sql.output} != ''"
          task_template:
            executor: llm
            prompt_id: text2sql.first_attempt
            config: {...}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .resolver import VariableResolver, VarContext

logger = logging.getLogger("workflow.dynamic")


class ForEachExecutor:
    """对列表的每个元素执行相同的 task 模板。

    payload:
        items: list              — 要遍历的列表（已由 VariableResolver 解析）。
        item_var: str = "item"   — 当前元素在子 task 中的变量名。
        task_template: dict      — 子 task 的配置模板。
    """

    async def execute(self, payload: Dict[str, Any]) -> List[Any]:
        """执行 ForEach 展开。

        实际上不直接执行子 task — 返回展开后的 task 定义列表，
        由 WorkflowRunner 负责提交执行。

        Returns:
            所有子 task 的执行结果列表。
        """
        items = payload.get("items", [])
        item_var = payload.get("item_var", "item")
        task_template = payload.get("task_template", {})

        if not isinstance(items, list):
            logger.warning(
                f"ForEachExecutor: 'items' is not a list, got {type(items)}"
            )
            return []

        logger.info(f"ForEachExecutor: expanding {len(items)} items")
        # 展开结果由 WorkflowRunner 处理 — 这里只返回模板信息
        return [
            {"index": i, "total": len(items), item_var: item}
            for i, item in enumerate(items)
        ]


class LoopExecutor:
    """重复执行子 task 直到条件满足。

    payload:
        max_iterations: int = 3     — 最大迭代次数。
        condition: str              — 继续循环的条件（${} 表达式）。
        task_template: dict         — 每次迭代执行的 task 模板。
        delay: float = 0            — 迭代间延迟（秒）。
    """

    def __init__(self):
        self._resolver = VariableResolver()

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Loop 本身不直接执行 — 展开逻辑由 WorkflowRunner 处理。

        Returns:
            元信息供 WorkflowRunner 消费。
        """
        return {
            "max_iterations": payload.get("max_iterations", 3),
            "condition": payload.get("condition", ""),
            "task_template": payload.get("task_template", {}),
            "delay": payload.get("delay", 0),
            "type": "loop_meta",
        }
