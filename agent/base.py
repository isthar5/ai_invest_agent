from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

class SkillResult(BaseModel):
    """技能执行结果"""
    success: bool
    data: Any
    error: Optional[str] = None

class BaseSkill(ABC):
    """技能抽象基类"""
    name: str
    description: str
    version: str = "1.0.0"

    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> SkillResult:
        """执行技能，接收 Agent 状态，返回结构化结果"""
        pass

    def get_metadata(self) -> Dict[str, str]:
        """返回技能元数据（用于 SKILL.md 生成）"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version
        }