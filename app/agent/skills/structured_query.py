# app/agent/skills/structured_query.py
import logging
from app.agent.base import BaseSkill, SkillResult
from app.agent.registry import SkillRegistry
from app.agent.schemas import StructuredQueryOutput

logger = logging.getLogger(__name__)

@SkillRegistry.register("structured_query")
class StructuredQuerySkill(BaseSkill):
    name = "structured_query"
    description = "执行结构化数据查询（Text2SQL），获取财务报表、行业排名等结构化历史数据"

    async def execute(self, state: dict) -> SkillResult:
        """
        执行结构化查询技能。
        优先使用 data_fetch_node 预取的 go_sql_raw。
        """
        go_sql_raw = state.get("go_sql_raw")
        
        if not go_sql_raw:
            # 如果预取失败或缺失，该技能无法单独工作（需要 Go-agent text2sql 模块）
            return SkillResult(
                success=False, 
                data={},
                error="结构化查询数据缺失，Go-agent text2sql 模块可能未就绪"
            )

        try:
            # 构建标准输出
            output = StructuredQueryOutput(
                sql=go_sql_raw.get("sql", ""),
                result=go_sql_raw.get("result"),
                explanation=go_sql_raw.get("explanation"),
                request_id=go_sql_raw.get("request_id")
            )
            return SkillResult(success=True, data=output.dict())
        except Exception as e:
            logger.error(f"StructuredQuerySkill 数据格式校验失败: {e}")
            return SkillResult(success=False, data={}, error=f"数据格式错误: {e}")
