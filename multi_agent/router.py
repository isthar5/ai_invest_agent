import asyncio

from app.multi_agent.base import AgentMessage, BaseAgent
from app.multi_agent.fusion import Fusion


class RouterAgent(BaseAgent):
    def __init__(self, agents: dict, llm=None):
        super().__init__("RouterAgent", None)
        self.agents = agents
        self.llm = llm

    async def run(self, msg: AgentMessage) -> AgentMessage:
        text = (msg.content or "").lower()

        if self.llm:
            intent = await self.llm.classify_intent(text)
        else:
            financial_keywords = ["财务", "财报", "年报", "季报", "营收", "利润", "financial"]
            industry_keywords = ["行业", "对比", "竞争", "industry", "peer"]
            sql_keywords = ["sql", "数据库", "查询", "营收数据", "利润数据", "table"]

            if any(keyword in text for keyword in sql_keywords):
                intent = "text2sql"
            elif any(keyword in text for keyword in financial_keywords):
                intent = "financial_analysis"
            elif any(keyword in text for keyword in industry_keywords):
                intent = "industry_comparison"
            else:
                intent = "rag_query"

        msg.metadata["intent"] = intent
        target_map = {
            "financial_analysis": ["QuantAgent"],
            "industry_comparison": ["QuantAgent"],
            "text2sql": ["Text2SQLAgent"],
            "rag_query": ["RAGAgent"],
        }
        target_names = target_map.get(intent, ["RAGAgent"])

        tasks = [
            asyncio.create_task(asyncio.wait_for(self.agents[name].run(msg), timeout=5))
            for name in target_names
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        aggregated = await Fusion.aggregate(results)
        msg.content = aggregated.content
        return msg
