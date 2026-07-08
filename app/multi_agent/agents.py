from app.multi_agent.base import BaseAgent, AgentMessage
from app.multi_agent.tools import TOOLS

def get_tool(name):
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None

class QuantAgent(BaseAgent):
    def __init__(self, state_manager):
        super().__init__("QuantAgent", state_manager)

    async def _process(self, msg: AgentMessage) -> dict:
        intent = msg.metadata.get("intent")
        stock = msg.metadata.get("stock")
        if intent == "financial_analysis":
            tool = get_tool("AnalyzeFinancials")
        elif intent == "industry_comparison":
            tool = get_tool("CompareIndustries")
        else:
            return {"error": f"Unknown intent {intent}"}
        return await tool.execute({"content": msg.content, "stock": stock})

class Text2SQLAgent(BaseAgent):
    def __init__(self, state_manager):
        super().__init__("Text2SQLAgent", state_manager)

    async def _process(self, msg: AgentMessage) -> dict:
        tool = get_tool("GenerateSQL")
        query = msg.content
        for attempt in range(2):
            try:
                return await tool.execute({"content": query})
            except Exception as e:
                query = f"修正 SQL: {query} 错误: {str(e)}"
        return {"error": "SQL generation failed twice"}

class RAGAgent(BaseAgent):
    def __init__(self, state_manager):
        super().__init__("RAGAgent", state_manager)

    async def _process(self, msg: AgentMessage) -> dict:
        tool_retrieve = get_tool("RAGRetrieve")
        tool_generate = get_tool("RAGGenerate")
        docs = await tool_retrieve.execute({"query": msg.content})
        return await tool_generate.execute({"query": msg.content, "docs": docs})
