# tests/e2e/test_multi_agent.py
import pytest
import asyncio
import time
from app.multi_agent.runtime import run_multi_agent

@pytest.mark.asyncio
async def test_multi_agent_quant():
    """测试 Multi-Agent 财报分析"""
    result = await run_multi_agent("万华化学财务分析", session_id="test_quant")
    assert result.get("success") is True
    assert "skill_results" in result

@pytest.mark.asyncio
async def test_multi_agent_latency():
    """测试 Multi-Agent 响应延迟"""
    latencies = []
    for _ in range(3):
        start = time.time()
        result = await run_multi_agent("万华化学", session_id="test_latency")
        elapsed = time.time() - start
        latencies.append(elapsed)
    
    avg_latency = sum(latencies) / len(latencies)
    print(f"\n⏱️ 平均响应延迟: {avg_latency:.2f}s")
    assert avg_latency < 10.0  # 不超过 10 秒

@pytest.mark.asyncio
async def test_multi_agent_router_activation():
    """测试 Router 正确激活 Agent"""
    test_cases = [
        ("万华化学财务分析", "QuantAgent"),
        ("查询营收数据", "Text2SQLAgent"),
        ("MDI产能扩张", "RAGAgent"),
    ]
    
    for query, expected_agent in test_cases:
        result = await run_multi_agent(query, session_id="test_router")
        skill_results = result.get("skill_results", {})
        # 检查对应 Agent 是否有输出
        print(f"Query: {query[:20]}... | Skills: {list(skill_results.keys())}")
        assert expected_agent in list(skill_results.keys())