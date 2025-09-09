#!/usr/bin/env python3
"""
项目设置脚本
"""

import subprocess
import sys
import shutil
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} 完成")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失败: {e}")
        if e.stderr:
            print(e.stderr)
        return False

def setup_environment():
    """设置开发环境"""
    print("🚀 开始设置智能自动化API生成平台...")
    
    # 安装依赖
    if not run_command("pip install -r requirements.txt", "安装Python依赖"):
        return False
    
    # 安装Playwright浏览器
    if not run_command("playwright install chromium", "安装Playwright浏览器"):
        return False
    
    # 复制配置文件
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if env_example.exists() and not env_file.exists():
        shutil.copy(env_example, env_file)
        print("✅ 已创建 .env 配置文件")
        print("📝 请编辑 .env 文件，配置您的 API_KEY、BASE_URL 和 MODEL_NAME")
    elif env_file.exists():
        print("ℹ️  .env 配置文件已存在")
    
    # 创建必要目录
    Path("sessions").mkdir(exist_ok=True)
    Path("generated_functions").mkdir(exist_ok=True)
    print("✅ 已创建必要目录")
    
    print("\n🎉 环境设置完成！")
    print("\n📋 下一步:")
    print("1. 编辑 .env 文件配置 API 密钥")
    print("2. 运行 python test_ai_config.py 测试AI配置")
    print("3. 运行 python main.py --help 查看可用命令")
    
    return True

if __name__ == "__main__":
    setup_environment()