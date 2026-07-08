"""
M4 — Artifact 持久化数据产物。

Artifact 是 task 产出的命名数据对象。与 context 不同：
  - context: 瞬态，仅在单次 workflow 执行中传递
  - artifact: 持久化，可跨 workflow run 共享，用于调试/审计/下游消费

ArtifactStore: 进程内 dict 存储。未来可替换为 S3/Redis/DB。

Usage:
    store = ArtifactStore()
    store.put("my_wf", "report", {"sql": "SELECT ...", "rows": [...]})
    artifact = store.get("my_wf", "report")

    # 在 YAML task 中声明产出:
    # config:
    #   produces: ["sql_result", "analysis_report"]
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("workflow.artifact")


# ═══════════════════════════════════════════════════════════════
#  Artifact
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Artifact:
    """单个数据产物。

    Attributes:
        name: 产物名（YAML 中声明）。
        workflow_id: 所属 workflow。
        task_id: 产出 task 的 id。
        version: 版本号（同一 workflow 内递增）。
        data: 产物数据。
        created_at: 创建时间戳。
    """

    name: str
    workflow_id: str
    task_id: str = ""
    version: int = 1
    data: Any = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "version": self.version,
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════════
#  ArtifactStore
# ═══════════════════════════════════════════════════════════════

class ArtifactStore:
    """进程内 Artifact 存储。

    Key: (workflow_id, artifact_name)
    支持多版本：同一 artifact 多次产出时自动递增 version。
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, List[Artifact]]] = {}
        # {workflow_id: {name: [Artifact v1, v2, ...]}}

    def put(
        self,
        workflow_id: str,
        name: str,
        data: Any,
        task_id: str = "",
    ) -> Artifact:
        """存储一个 Artifact。版本自动递增。

        Args:
            workflow_id: workflow 标识。
            name: 产物名。
            data: 产物数据。
            task_id: 产出 task。

        Returns:
            创建的 Artifact 实例。
        """
        if workflow_id not in self._store:
            self._store[workflow_id] = {}

        versions = self._store[workflow_id].get(name, [])
        version = len(versions) + 1

        artifact = Artifact(
            name=name,
            workflow_id=workflow_id,
            task_id=task_id,
            version=version,
            data=data,
        )
        versions.append(artifact)
        self._store[workflow_id][name] = versions

        logger.debug(
            f"ArtifactStore: '{workflow_id}/{name}' v{version} stored "
            f"(task={task_id})"
        )
        return artifact

    def get(
        self,
        workflow_id: str,
        name: str,
        version: int = -1,
    ) -> Optional[Artifact]:
        """获取 Artifact。

        Args:
            workflow_id: workflow 标识。
            name: 产物名。
            version: 版本号。-1 表示最新版本。

        Returns:
            Artifact 或 None。
        """
        versions = self._store.get(workflow_id, {}).get(name, [])
        if not versions:
            return None
        if version == -1:
            return versions[-1]
        if 1 <= version <= len(versions):
            return versions[version - 1]
        return None

    def list_names(self, workflow_id: str) -> List[str]:
        """列出 workflow 下所有 artifact 名称。"""
        return list(self._store.get(workflow_id, {}).keys())

    def clear(self, workflow_id: str) -> None:
        """清空 workflow 的所有 artifact。"""
        self._store.pop(workflow_id, None)

    def to_context(self, workflow_id: str) -> Dict[str, Any]:
        """将所有 artifact 的快照转为 context 可用的 dict。

        Returns:
            {name: latest_data, ...}
        """
        return {
            name: versions[-1].data
            for name, versions in self._store.get(workflow_id, {}).items()
            if versions
        }
