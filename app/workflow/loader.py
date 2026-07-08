"""
WorkflowLoader — YAML → WorkflowDefinition。

M1 设计:
  - 单文件单 Workflow（文件名 = workflow_id）
  - 不拆分 Parser / Validator（只有 1-2 个 YAML）
  - 不做变量解析（M2 VariableResolver）
  - 内联结构校验
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml

from .models import TaskDefinition, WorkflowDefinition

logger = logging.getLogger("workflow.loader")


class WorkflowLoader:
    """从 YAML 文件加载 WorkflowDefinition。"""

    def __init__(self, config_dir: Path):
        self._config_dir = Path(config_dir)

    # ── 公共 API ──────────────────────────────────────────

    def load(self, workflow_id: str) -> WorkflowDefinition:
        """加载指定 Workflow。

        Raises:
            FileNotFoundError: YAML 文件不存在。
            ValueError: YAML 结构不合法。
        """
        path = self._config_dir / f"{workflow_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Workflow config not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("YAML root must be a dict")

        return self._parse(workflow_id, data)

    def load_all(self) -> Dict[str, WorkflowDefinition]:
        """加载目录下全部 .yaml 文件。"""
        definitions: Dict[str, WorkflowDefinition] = {}
        if not self._config_dir.exists():
            return definitions
        for path in sorted(self._config_dir.glob("*.yaml")):
            try:
                wf = self.load(path.stem)
                definitions[wf.workflow_id] = wf
            except Exception as e:
                logger.error(f"Failed to load {path.name}: {e}")
        return definitions

    # ── 解析 ──────────────────────────────────────────────

    def _parse(self, workflow_id: str, data: Dict[str, Any]) -> WorkflowDefinition:
        """YAML dict → WorkflowDefinition。

        YAML 结构:
          meta:
            version: "1.0"
          tasks:
            <task_id>:
              executor: llm
              depends_on: [a, b]    # 可选
              config: {...}          # executor 特定
        """
        meta = data.get("meta", {})
        version = str(meta.get("version", "1.0"))

        tasks_data = data.get("tasks")
        if not isinstance(tasks_data, dict):
            raise ValueError("'tasks' must be a dict")

        tasks = tuple(
            self._parse_task(task_id, task_data)
            for task_id, task_data in tasks_data.items()
        )

        definition = WorkflowDefinition(
            workflow_id=workflow_id,
            version=version,
            tasks=tasks,
        )

        self._validate(definition)
        logger.info(f"WorkflowLoader: loaded '{workflow_id}' ({len(tasks)} tasks)")
        return definition

    @staticmethod
    def _parse_task(task_id: str, data: Dict[str, Any]) -> TaskDefinition:
        executor = data.get("executor")
        if not executor:
            raise ValueError(f"Task '{task_id}': 'executor' is required")

        depends_on_raw = data.get("depends_on")
        if depends_on_raw is None:
            depends_on = ()
        elif isinstance(depends_on_raw, list):
            depends_on = tuple(str(d) for d in depends_on_raw)
        else:
            depends_on = (str(depends_on_raw),)

        return TaskDefinition(
            id=str(task_id),
            executor=str(executor),
            depends_on=depends_on,
            config=dict(data.get("config", {})),
        )

    # ── 校验 ──────────────────────────────────────────────

    @staticmethod
    def _validate(definition: WorkflowDefinition) -> None:
        """校验 depends_on 引用的 task id 存在。"""
        task_ids = set(definition.task_ids)
        for task in definition.tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task '{task.id}' depends_on '{dep}', "
                        f"but '{dep}' is not defined"
                    )
