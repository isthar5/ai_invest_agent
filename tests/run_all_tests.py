# tests/run_all_tests.py
import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def main():
    start_time = datetime.now()
    print(f"🚀 CI/CD 自动化测试开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_passed = True
    
    # 1. 代码规范检查
    if not run_command("ruff check app/ --select E,F,W", "代码规范检查 (Ruff)"):
        all_passed = False
    
    # 2. 单元测试
    if not run_command("pytest tests/unit/ -v --tb=short", "单元测试"):
        all_passed = False
    
    # 3. 集成测试（检索）
    if not run_command("pytest tests/integration/test_retrieval.py -v --tb=short", "检索集成测试"):
        all_passed = False
    
    # 4. 端到端测试
    if not run_command("pytest tests/e2e/test_multi_agent.py -v --tb=short", "端到端测试"):
        all_passed = False
    
    # 5. 生成测试报告
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\n{'='*60}")
    print(f"📋 测试报告")
    print(f"{'='*60}")
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {duration:.2f}s")
    print(f"测试结果: {'✅ 全部通过' if all_passed else '❌ 存在失败'}")
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()