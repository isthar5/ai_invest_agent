"""
M4 — Saga 补偿事务模式。

当 workflow 中某个 task 失败时，逆序执行之前成功 task 的补偿动作。
每个 task 可通过 YAML 中的 on_failure 字段声明其补偿 task id。

补偿规则:
  - 按执行顺序的逆序执行补偿
  - 补偿 task 只执行一次（即使原 task 重试了多次）
  - 补偿失败只记日志，不中断补偿链
  - 补偿完成后 workflow 状态标记为 "compensated"

Usage (YAML):
    tasks:
      reserve_inventory:
        executor: skill
        skill: reserve_inventory
        config:
          item_id: "${params.item_id}"
        on_failure: release_inventory   # ← 补偿 task id

      release_inventory:
        executor: skill
        skill: release_inventory
        config:
          item_id: "${params.item_id}"
        # 这个 task 只在补偿时执行，不在正常流程中
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.runtime.task import Task

logger = logging.getLogger("workflow.saga")


class SagaManager:
    """Saga 补偿管理器。

    追踪已执行 task 的顺序，在失败时逆序执行补偿。
    """

    def __init__(self):
        # 执行历史: [{"task_id": str, "on_failure": str | None, "payload": dict}]
        self._history: List[Dict[str, Any]] = []
        self._compensated: bool = False

    def record(
        self,
        task_id: str,
        on_failure: str,
        payload: Dict[str, Any],
    ) -> None:
        """记录一个已成功执行的 task。

        Args:
            task_id: task id。
            on_failure: 补偿 task id（可为空）。
            payload: task payload（传给补偿 task）。
        """
        if on_failure:
            self._history.append({
                "task_id": task_id,
                "on_failure": on_failure,
                "payload": dict(payload),
            })
            logger.debug(
                f"Saga: recorded '{task_id}' → compensate='{on_failure}'"
            )

    @property
    def has_compensations(self) -> bool:
        """是否有待执行的补偿。"""
        return len(self._history) > 0

    @property
    def is_compensated(self) -> bool:
        return self._compensated

    def get_compensation_tasks(self) -> List[Dict[str, Any]]:
        """获取补偿 task 列表（逆序）。

        Returns:
            [{"task_id": str, "compensate_id": str, "payload": dict}, ...]
            按执行逆序排列。
        """
        compensations = []
        for entry in reversed(self._history):
            compensations.append({
                "task_id": entry["task_id"],
                "compensate_id": entry["on_failure"],
                "payload": entry["payload"],
            })
        return compensations

    def mark_compensated(self) -> None:
        """标记补偿已完成。"""
        self._compensated = True
        logger.info(
            f"Saga: compensation complete ({len(self._history)} actions)"
        )

    def clear(self) -> None:
        """清空历史。"""
        self._history.clear()
        self._compensated = False
