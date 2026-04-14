# tests/test_agent_integration.py
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.runtime import run_agent
from app.rag.pipeline import rag_quant_pipeline


async def test_agent_full_pipeline():
    """测试 Agent 完整流程"""
    print("\n" + "=" * 60)
    print("🚀 Agent 集成测试 - 万华化学财报分析")
    print("=" * 60)

    query = "分析一下万华化学的财务状况和行业地位"

    print(f"\n📝 查询: {query}")
    print("\n⏳ 执行中...\n")

    try:
        result = await run_agent(query)

        print("\n✅ Agent 执行成功!")
        print(f"\n📊 选中的技能: {result['selected_skills']}")
        print(f"\n📁 技能执行结果键: {list(result['skill_results'].keys())}")

        if result.get("error"):
            print(f"\n⚠️ 部分错误: {result['error']}")

        print("\n" + "-" * 40)
        print("📄 最终回答预览 (前500字符):")
        print("-" * 40)
        answer = result.get("answer", "")
        print(answer[:500] + "..." if len(answer) > 500 else answer)

        return result

    except Exception as e:
        print(f"\n❌ Agent 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_rag_pipeline_comparison():
    """对比原有 RAG 流程"""
    print("\n" + "=" * 60)
    print("🔄 对比测试 - 原有 RAG+Quant 流程")
    print("=" * 60)

    query = "万华化学财务分析"

    try:
        result = await rag_quant_pipeline(query, streaming=False)
        print("\n✅ RAG 流程执行成功!")
        print(f"\n📄 回答预览: {result.get('answer', '')[:300]}...")
        return result
    except Exception as e:
        print(f"\n❌ RAG 流程失败: {e}")
        return None


async def test_trace_log():
    """检查追踪日志"""
    print("\n" + "=" * 60)
    print("📋 检查 Agent 追踪日志")
    print("=" * 60)

    trace_path = Path(__file__).parent.parent / "agent_traces.jsonl"
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"\n✅ 找到 {len(lines)} 条追踪记录")
            if lines:
                import json
                last = json.loads(lines[-1])
                print(f"\n最新记录:")
                print(f"  时间: {last.get('timestamp')}")
                print(f"  节点: {last.get('node')}")
                print(f"  技能: {last.get('selected_skills')}")
                print(f"  错误: {last.get('error') or '无'}")
    else:
        print(f"\n⚠️ 追踪日志不存在: {trace_path}")


async def main():
    print("\n" + "🧪" * 30)
    print("AI Invest Agent 集成测试套件")
    print("🧪" * 30)

    # 测试1: Agent 完整流程
    agent_result = await test_agent_full_pipeline()

    # 测试2: 原有流程对比
    rag_result = await test_rag_pipeline_comparison()

    # 测试3: 追踪日志
    await test_trace_log()

    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"Agent 模式: {'✅ 通过' if agent_result else '❌ 失败'}")
    print(f"RAG 模式:  {'✅ 通过' if rag_result else '❌ 失败'}")


if __name__ == "__main__":
    asyncio.run(main())