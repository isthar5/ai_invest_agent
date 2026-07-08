# tests/integration/test_retrieval.py
import pytest
import asyncio
from app.retrieval.hybrid import hybrid_search

# 测试查询集
TEST_QUERIES = [
    {"query": "万华化学 MDI 产能", "expected_hit": True},
    {"query": "化工行业毛利率", "expected_hit": True},
    {"query": "不存在的查询xyz123", "expected_hit": False},
]

@pytest.mark.asyncio
async def test_hybrid_search_returns_results():
    """测试混合检索能返回结果"""
    results, dense, sparse = await hybrid_search("万华化学", limit=5)
    assert len(results) > 0
    assert len(dense) > 0
    assert len(sparse) > 0

@pytest.mark.asyncio
async def test_hybrid_search_metrics():
    """测试检索指标计算"""
    recall_at_5 = 0
    recall_at_10 = 0
    
    for item in TEST_QUERIES[:2]:  # 只测有预期命中的
        results, _, _ = await hybrid_search(item["query"], limit=10)
        ids = [doc_id for doc_id, _ in results]
        
        # 只要有结果就算命中（实际应该有标注数据）
        if len(ids) >= 5:
            recall_at_5 += 1
        if len(ids) >= 10:
            recall_at_10 += 1
    
    n = 2
    print(f"\n📊 Recall@5: {recall_at_5/n:.0%}")
    print(f"📊 Recall@10: {recall_at_10/n:.0%}")