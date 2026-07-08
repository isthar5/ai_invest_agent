"""
WorkflowRegistry — WorkflowDefinition 注册中心。

与 PromptRegistry 同模式:
  - 单例（模块级 get_registry）
  - 延迟加载（首次 get 时加载全部 YAML）
  - 热更新（reload 替换缓存）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

from .loader import WorkflowLoader
from .models import WorkflowDefinition

logger = logging.getLogger("workflow.registry")

_DEFAULT_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "workflows"


class WorkflowRegistry:
    """Workflow 注册中心（单例）。"""

    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or _DEFAULT_DIR
        self._loader = WorkflowLoader(self._config_dir)
        self._definitions: Dict[str, WorkflowDefinition] = {}
        self._loaded = False

    # ── 公共 API ──────────────────────────────────────────

    def get(self, workflow_id: str) -> WorkflowDefinition:
        """获取 WorkflowDefinition。首次调用触发延迟加载。"""
        if not self._loaded:
            self._load()
        if workflow_id not in self._definitions:
            raise KeyError(
                f"Workflow '{workflow_id}' not found. "
                f"Available: {list(self._definitions.keys())}"
            )
        return self._definitions[workflow_id]

    def list_ids(self) -> list:
        """列出所有 workflow id。"""
        if not self._loaded:
            self._load()
        return sorted(self._definitions.keys())

    def reload(self) -> bool:
        """热更新：重新加载全部 YAML。失败保留旧缓存。"""
        try:
            new = self._loader.load_all()
            if not new:
                logger.warning("WorkflowRegistry.reload: empty, keeping old")
                return False
            self._definitions = new
            self._loaded = True
            logger.info(f"WorkflowRegistry.reload: {len(new)} workflows")
            return True
        except Exception as e:
            logger.error(f"WorkflowRegistry.reload failed: {e}")
            return False

    # ── 内部 ──────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._definitions = self._loader.load_all()
            self._loaded = True
            logger.info(f"WorkflowRegistry: {len(self._definitions)} workflows loaded")
        except Exception as e:
            logger.error(f"WorkflowRegistry: load failed: {e}")
            self._definitions = {}
            self._loaded = True


# ═══════════════════════════════════════════════════════════════
#  模块级单例
# ═══════════════════════════════════════════════════════════════

_registry: Optional[WorkflowRegistry] = None


def get_registry(config_dir: Optional[Path] = None) -> WorkflowRegistry:
    global _registry
    if _registry is None:
        _registry = WorkflowRegistry(config_dir=config_dir)
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
