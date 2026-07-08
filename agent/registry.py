from typing import Dict, Type, Optional
from app.agent.base import BaseSkill

class SkillRegistry:
    """技能注册中心（单例）"""
    _skills: Dict[str, Type[BaseSkill]] = {}

    @classmethod
    def register(cls, name: str):
        """装饰器：注册技能"""
        def decorator(skill_cls: Type[BaseSkill]):
            cls._skills[name] = skill_cls
            return skill_cls
        return decorator

    @classmethod
    def get_skill(cls, name: str) -> Optional[Type[BaseSkill]]:
        return cls._skills.get(name)

    @classmethod
    def list_skills(cls) -> list:
        return list(cls._skills.keys())