#!/usr/bin/env python3
"""
运行项目测试
"""

import subprocess
import sys
from pathlib import Path

def run_tests():
    """运行所有测试"""
    print("🧪 运行项目测试...")
    
    # 检查是否安装了pytest
    try:
        import pytest
    except ImportError:
        print("❌ pytest 未安装，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest"], check=True)
    
    # 运行基础测试
    test_files = list(Path("tests").glob("*.py"))
    if test_files:
        print("📋 运行单元测试...")
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], 
                              capture_output=False)
        if result.returncode == 0:
            print("✅ 单元测试通过")
        else:
            print("❌ 单元测试失败")
            return False
    else:
        print("⚠️  未找到测试文件")
    
    # 运行AI配置测试
    print("\n🤖 测试AI配置...")
    result = subprocess.run([sys.executable, "test_ai_config.py"], 
                          capture_output=False)
    
    if result.returncode == 0:
        print("✅ 所有测试通过")
        return True
    else:
        print("❌ 测试失败")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)