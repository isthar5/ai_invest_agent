# test_memory.py
import asyncio
import sys
sys.path.insert(0, '.')

from app.agent.memory import ShortTermMemory, LongTermMemory

async def test():
    # 测试短期记忆
    short = ShortTermMemory()
    await short.add("test_session", {"query": "万华化学营收", "answer": "1820亿"})
    await short.add("test_session", {"query": "净利润呢", "answer": "210亿"})

    history = await short.get("test_session")
    print("短期记忆:", history)

    # 测试长期记忆
    long = LongTermMemory()
    await long.update("user_001", {"preferred_industry": "化工", "risk_level": "moderate"})
    prefs = await long.get("user_001")
    print("长期记忆:", prefs)

    # 清理
    await short.clear("test_session")
    await long.clear("user_001")

if __name__ == "__main__":
    asyncio.run(test())