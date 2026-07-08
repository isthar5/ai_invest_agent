# tests/conftest.py
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio

@pytest.fixture(scope="session")
def event_loop():
    """创建会话级事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()