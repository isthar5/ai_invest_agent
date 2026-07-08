import asyncio
from app.agent.runtime import data_fetch_node, AgentState

async def test():
    state = AgentState(query="万华化学 财报", stock="600309")
    state = await data_fetch_node(state)
    print("Quant:", state.go_quant_raw)
    print("RAG:", "有数据" if state.go_rag_raw else "无数据")

asyncio.run(test())