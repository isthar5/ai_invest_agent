import asyncio
from typing import Dict


class Tool:
    def __init__(self, name: str, description: str, func):
        self.name = name
        self.description = description
        self.func = func

    async def execute(self, input: Dict):
        try:
            if asyncio.iscoroutinefunction(self.func):
                return await self.func(**input)
            return await asyncio.to_thread(self.func, **input)
        except Exception as e:
            return {"error": str(e)}


async def analyze_financials(content: str, stock: str = None):
    try:
        from app.agent.skills.financial_analysis import FinancialAnalysisSkill

        skill = FinancialAnalysisSkill()
        result = await skill.execute({"query": content, "stock": stock})
        return result.data if result.success else {"error": result.error}
    except Exception:
        company = stock or content[:20]
        return {
            "summary": f"{company} 财务分析已触发，当前处于降级模式。",
            "insight": f"已由 QuantAgent 接管查询：{content}",
            "mode": "fallback",
        }


async def compare_industries(content: str, stock: str = None):
    try:
        from app.agent.skills.industry_comparison import IndustryComparisonSkill

        skill = IndustryComparisonSkill()
        result = await skill.execute({"query": content, "stock": stock})
        return result.data if result.success else {"error": result.error}
    except Exception:
        return {
            "summary": f"行业对比已触发，当前处于降级模式：{content}",
            "mode": "fallback",
        }


async def generate_sql(content: str):
    try:
        from app.agent.go_tool_client import GoToolClient

        client = GoToolClient()
        return client.call("text2sql", {"query": content, "user": "multi_agent"})
    except Exception as e:
        return {
            "sql": "SELECT * FROM financials LIMIT 10;",
            "explanation": f"Text2SQL 降级返回，占位原因: {str(e)}",
            "mode": "fallback",
        }


async def rag_retrieve(query: str):
    try:
        from app.retrieval.hybrid import hybrid_search

        results, _, _ = await hybrid_search(query, limit=10)
        return results
    except Exception:
        return []


async def rag_generate(query: str, docs: list):
    return {"answer": f"基于检索结果生成的回答: {query}", "docs_count": len(docs or [])}


TOOLS = [
    Tool("AnalyzeFinancials", "Analyze company financials", analyze_financials),
    Tool("CompareIndustries", "Compare industry metrics", compare_industries),
    Tool("GenerateSQL", "Generate SQL query from NL", generate_sql),
    Tool("RAGRetrieve", "Retrieve documents", rag_retrieve),
    Tool("RAGGenerate", "Generate answer from docs", rag_generate),
]
