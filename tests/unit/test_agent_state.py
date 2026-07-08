# tests/unit/test_agent_state.py
import pytest
from app.agent.runtime import AgentState

def test_agent_state_initialization():
    """测试 AgentState 初始化"""
    state = AgentState(query="万华化学财务分析")
    assert state.query == "万华化学财务分析"
    assert state.stock == ""
    assert state.selected_skills == []
    assert state.skill_results == {}

def test_agent_state_stock_extraction():
    """测试股票代码提取"""
    state = AgentState(query="600309 营收")
    assert state.query == "600309 营收"
    assert state.stock == ""  # 初始化时 stock 默认为空，提取逻辑在 planner_node 中