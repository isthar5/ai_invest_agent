"""
M4 — Checkpoint 工作流检查点与恢复。

Checkpoint 在每次 task 完成后自动保存工作流状态快照。
如果 workflow 中断（进程重启/异常），可从最近的 checkpoint 恢复。

CheckpointManager: 内存存储。未来可持久化到文件/Redis/DB。

Usage:
    mgr = CheckpointManager()
    cp = mgr.save("text2sql", completed={"schema_link"}, ctx_snapshot={...})
    # ... after restart ...
    cp = mgr.load_latest("text2sql")
    runner.resume_from(plan, cp)  # 跳过已完成 task，恢复 context
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("workflow.checkpoint")


# ═══════════════════════════════════════════════════════════════
#  Checkpoint
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Checkpoint:
    """工作流状态快照。

    Attributes:
        checkpoint_id: 唯一标识。
        workflow_id: workflow 标识。
        run_id: 本次执行的 run id（区分多次执行）。
        completed_tasks: 已完成的 task id 集合。
        context_snapshot: VarContext 的序列化快照。
        artifact_snapshot: Artifact 数据快照。
        seq: 递增序号（越大越新）。
        created_at: 创建时间戳。
    """

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    workflow_id: str = ""
    run_id: str = ""
    completed_tasks: Set[str] = field(default_factory=set)
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    artifact_snapshot: Dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "completed_tasks": list(self.completed_tasks),
            "seq": self.seq,
            "created_at": self.created_at,
        }


# ═══════════════════════════════════════════════════════════════
#  CheckpointManager
# ═══════════════════════════════════════════════════════════════

class CheckpointManager:
    """Checkpoint 管理器（内存存储）。

    每个 workflow_id 保留最近 N 个 checkpoint。
    """

    def __init__(self, max_checkpoints: int = 10):
        self._max = max_checkpoints
        self._store: Dict[str, List[Checkpoint]] = {}
        self._seq: Dict[str, int] = {}

    def save(
        self,
        workflow_id: str,
        run_id: str,
        completed_tasks: Set[str],
        context_snapshot: Dict[str, Any],
        artifact_snapshot: Dict[str, Any],
    ) -> Checkpoint:
        """保存一个 Checkpoint。

        Args:
            workflow_id: workflow 标识。
            run_id: 本次 run id。
            completed_tasks: 已完成的 task id 集合。
            context_snapshot: 当前 context 快照。
            artifact_snapshot: 当前 artifact 快照。

        Returns:
            创建的 Checkpoint。
        """
        if workflow_id not in self._store:
            self._store[workflow_id] = []
            self._seq[workflow_id] = 0

        self._seq[workflow_id] += 1
        cp = Checkpoint(
            workflow_id=workflow_id,
            run_id=run_id,
            completed_tasks=set(completed_tasks),
            context_snapshot=dict(context_snapshot),
            artifact_snapshot=dict(artifact_snapshot),
            seq=self._seq[workflow_id],
        )

        self._store[workflow_id].append(cp)

        # 限制数量
        if len(self._store[workflow_id]) > self._max:
            self._store[workflow_id] = self._store[workflow_id][-self._max:]

        logger.debug(
            f"CheckpointManager: saved #{cp.seq} for '{workflow_id}' "
            f"({len(cp.completed_tasks)} completed)"
        )
        return cp

    def load_latest(
        self, workflow_id: str, run_id: str = ""
    ) -> Optional[Checkpoint]:
        """加载最新的 Checkpoint。

        Args:
            workflow_id: workflow 标识。
            run_id: 可选，匹配特定 run。

        Returns:
            最新的 Checkpoint 或 None。
        """
        checkpoints = self._store.get(workflow_id, [])
        if not checkpoints:
            return None

        if run_id:
            matching = [c for c in checkpoints if c.run_id == run_id]
            return matching[-1] if matching else None

        return checkpoints[-1]

    def list_checkpoints(self, workflow_id: str) -> List[Dict[str, Any]]:
        """列出 workflow 的所有 checkpoint。"""
        return [c.to_dict() for c in self._store.get(workflow_id, [])]

    def clear(self, workflow_id: str) -> None:
        """清空 workflow 的所有 checkpoint。"""
        self._store.pop(workflow_id, None)
        self._seq.pop(workflow_id, None)
