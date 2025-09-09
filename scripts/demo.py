#!/usr/bin/env python3
"""
运行演示示例
"""

import subprocess
import sys
from datetime import datetime

def run_demo():
    """运行完整的演示流程"""
    print("🎬 智能自动化API生成平台 - 演示模式")
    print("=" * 50)
    
    # 生成演示会话名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_name = f"demo_{timestamp}"
    
    print("📋 演示流程:")
    print("1. 录制网页操作")
    print("2. AI分析会话")
    print("3. 测试生成的函数")
    print("4. 生成Python代码")
    print()
    
    # 步骤1: 录制
    print("🎬 步骤1: 开始录制...")
    print("即将打开浏览器，请在浏览器中执行您的操作，完成后按 Ctrl+C 结束录制")
    input("按回车键继续...")
    
    cmd = f'python main.py record --name "{session_name}" --url "https://httpbin.org/forms/post"'
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode != 0:
        print("❌ 录制失败")
        return False
    
    # 获取会话ID（假设是最新创建的）
    print("\n📋 获取会话列表...")
    result = subprocess.run("python main.py list", shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("❌ 获取会话列表失败")
        return False
    
    # 这里应该解析输出获取会话ID，简化处理
    print("✅ 录制完成")
    
    # 询问是否继续
    if not input("\n继续演示? (y/N): ").lower().startswith('y'):
        return True
    
    # 步骤2: 分析
    print("\n🤖 步骤2: AI分析...")
    session_id = input("请输入会话ID (从上面的列表中选择): ")
    
    if session_id:
        cmd = f'python main.py analyze --session "{session_id}"'
        result = subprocess.run(cmd, shell=True)
        
        if result.returncode == 0:
            print("✅ AI分析完成")
        else:
            print("❌ AI分析失败")
            return False
    
    # 询问是否继续
    if not input("\n继续演示? (y/N): ").lower().startswith('y'):
        return True
    
    # 步骤3: 测试
    print("\n🧪 步骤3: 测试函数...")
    params = input("输入测试参数 (格式: key=value,key2=value2，可留空): ")
    
    cmd = f'python main.py test --session "{session_id}"'
    if params:
        cmd += f' --params "{params}"'
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print("✅ 测试完成")
    else:
        print("⚠️  测试可能失败，这很正常")
    
    # 步骤4: 生成代码
    print("\n🚀 步骤4: 生成Python函数...")
    output_file = f"generated_functions/{session_name}.py"
    
    cmd = f'python main.py generate --session "{session_id}" --output "{output_file}"'
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print(f"✅ 函数已生成: {output_file}")
        print("\n🎉 演示完成！")
        print("您可以查看生成的Python文件并在自己的项目中使用。")
    else:
        print("❌ 代码生成失败")
        return False
    
    return True

def quick_demo():
    """快速演示模式"""
    print("⚡ 快速演示模式")
    print("这将展示主要命令的使用方法\n")
    
    commands = [
        ("查看帮助", "python main.py --help"),
        ("列出会话", "python main.py list"),
        ("测试AI配置", "python test_ai_config.py"),
    ]
    
    for desc, cmd in commands:
        print(f"🔍 {desc}:")
        print(f"   {cmd}")
        if input("   执行此命令? (y/N): ").lower().startswith('y'):
            subprocess.run(cmd, shell=True)
        print()

def main():
    """主函数"""
    print("🎬 智能自动化API生成平台 - 演示")
    print("=" * 40)
    print("请选择演示模式:")
    print("1. 🚀 启动交互式界面（推荐）")
    print("2. 🧪 测试系统功能")
    print("3. 📖 查看快速帮助")
    print("4. 👋 退出")
    
    choice = input("选择 (1-4): ")
    
    if choice == "1":
        print("🚀 启动交互式界面...")
        subprocess.run("python app.py", shell=True)
    elif choice == "2":
        print("🧪 运行系统测试...")
        subprocess.run("python scripts/test.py", shell=True)
    elif choice == "3":
        show_help()
    else:
        print("👋 退出演示")

def show_help():
    """显示帮助信息"""
    help_text = """
🎯 快速开始指南

1. 启动程序:
   python app.py

2. 选择"新建录制会话"

3. 配置录制参数:
   - 输入会话名称（如：login_demo）  
   - 输入目标URL（如：https://example.com）
   - 选择是否需要前置登录

4. 在打开的浏览器中执行操作

5. 按 Ctrl+C 结束录制

6. 选择"AI分析"自动识别参数

7. 选择"测试"验证生成的函数

8. 选择"生成函数"输出Python代码

💡 提示：
- 前置登录功能可以避免重复录制登录步骤
- AI会自动识别可变的输入参数
- 生成的代码包含完整的错误处理
"""
    print(help_text)

if __name__ == "__main__":
    main()