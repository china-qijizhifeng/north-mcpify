"""
命令行交互界面
处理用户交互和测试执行
"""

import asyncio
from typing import Dict, Optional
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.syntax import Syntax

from playwright.async_api import async_playwright
from src.session.manager import SessionManager
from src.ai.analyzer import AIAnalyzer

console = Console()

class CLIInterface:
    """命令行交互界面"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.ai_analyzer = AIAnalyzer()
    
    async def test_session(self, session_id: str, test_params: Dict) -> bool:
        """测试会话的AI生成函数"""
        session_data = self.session_manager.load_session(session_id)
        if not session_data:
            console.print("❌ 会话不存在", style="bold red")
            return False
        
        # 检查是否已经分析过
        if not session_data.get('ai_analysis', {}).get('analyzed'):
            console.print("⚠️  会话尚未分析，请先运行 analyze 命令", style="yellow")
            return False
        
        analysis = session_data['ai_analysis']
        suggested_params = analysis.get('suggested_parameters', [])
        
        # 收集缺失的参数
        if not test_params:
            console.print("📝 请输入测试参数:")
            for param in suggested_params:
                if param['required']:
                    value = Prompt.ask(f"{param['name']} ({param['description']})")
                    test_params[param['name']] = value
        
        console.print("🚀 开始执行测试...")
        
        try:
            success = await self._execute_test(session_data, test_params)
            return success
        except Exception as e:
            console.print(f"❌ 测试执行失败: {e}", style="bold red")
            return False
    
    async def _execute_test(self, session_data: Dict, params: Dict) -> bool:
        """执行测试"""
        operations = session_data.get('operations', [])
        auth_file = f"sessions/{session_data['session_id']}/auth_state.json"
        
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            
            # 恢复认证状态
            context = await browser.new_context(storage_state=auth_file)
            page = await context.new_page()
            
            try:
                # 导航到起始页面
                start_url = session_data['metadata']['url']
                await page.goto(start_url)
                
                console.print(f"🌐 已导航到: {start_url}")
                
                # 执行操作
                for operation in operations:
                    await self._execute_operation(page, operation, params)
                
                console.print("✅ 所有操作执行完成")
                
                # 等待用户确认
                result = Confirm.ask("测试执行成功，结果是否符合预期?")
                
                await browser.close()
                return result
                
            except Exception as e:
                await browser.close()
                raise e
    
    async def _execute_operation(self, page, operation: Dict, params: Dict):
        """执行单个操作"""
        action = operation['action']
        selector = operation['selector']
        value = operation.get('value', '')
        
        # 参数替换
        for param_name, param_value in params.items():
            value = value.replace(f"{{{param_name}}}", str(param_value))
        
        console.print(f"🎯 执行 {action}: {selector}")
        
        try:
            if action == 'click':
                await page.click(selector, timeout=5000)
            elif action == 'input':
                await page.fill(selector, value, timeout=5000)
            elif action == 'navigation':
                await page.goto(value, timeout=10000)
            
            # 等待页面稳定
            await page.wait_for_timeout(1000)
            
        except Exception as e:
            console.print(f"⚠️  操作失败: {e}", style="yellow")
            # 尝试替代方案
            await self._try_alternative_selector(page, operation)
    
    async def _try_alternative_selector(self, page, operation: Dict):
        """尝试替代选择器"""
        text_content = operation.get('text_content', '')
        if text_content:
            try:
                # 尝试通过文本内容查找
                await page.click(f"text={text_content}", timeout=3000)
                console.print(f"✅ 使用文本选择器成功: {text_content}")
            except:
                console.print(f"❌ 替代选择器也失败", style="red")
    
    async def interactive_refinement(self, session_id: str):
        """交互式优化会话"""
        session_data = self.session_manager.load_session(session_id)
        if not session_data:
            console.print("❌ 会话不存在", style="bold red")
            return
        
        console.print(Panel(
            "🔧 交互优化模式\n"
            "您可以通过自然语言描述需要修改的地方\n"
            "例如: '添加错误处理', '修改参数类型', '优化选择器'",
            title="优化助手",
            border_style="blue"
        ))
        
        while True:
            instruction = Prompt.ask("\n💬 请描述需要修改的地方 (输入 'quit' 退出)")
            
            if instruction.lower() in ['quit', 'exit', 'q']:
                break
            
            # 调用AI进行代码优化
            console.print("🤖 正在优化代码...")
            
            try:
                optimized_result = await self.ai_analyzer.refine_analysis(
                    session_data, instruction
                )
                
                # 显示优化结果
                self._display_optimization_result(optimized_result)
                
                # 用户确认
                if Confirm.ask("是否接受这个优化?"):
                    # 更新会话数据
                    session_data['ai_analysis'].update(optimized_result)
                    self.session_manager.save_analysis(session_id, optimized_result)
                    console.print("✅ 优化已保存", style="green")
                else:
                    console.print("❌ 优化已取消", style="yellow")
                    
            except Exception as e:
                console.print(f"❌ 优化失败: {e}", style="red")
        
        console.print("👋 退出优化模式")
    
    def _display_optimization_result(self, result: Dict):
        """显示优化结果"""
        if 'function_signature' in result:
            console.print("\n📝 新的函数签名:")
            syntax = Syntax(result['function_signature'], "python", theme="monokai")
            console.print(syntax)
        
        if 'suggested_parameters' in result:
            console.print("\n🔧 更新的参数:")
            for param in result['suggested_parameters']:
                console.print(f"  • {param['name']}: {param['type']} - {param['description']}")
        
        if 'improvements' in result:
            console.print(f"\n✨ 改进说明: {result['improvements']}")