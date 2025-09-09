"""
交互式CLI界面
提供美观的菜单系统和用户友好的交互体验
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
import time

from src.recording.recorder import WebRecorder
from src.session.manager import SessionManager
from src.ai.analyzer import AIAnalyzer
from src.cli.interface import CLIInterface
from src.utils.config import Config
import json

console = Console()

class InteractiveCLI:
    """交互式命令行界面"""
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.ai_analyzer = AIAnalyzer()
        self.cli_interface = CLIInterface()
        self.current_session = None
    
    def display_welcome(self):
        """显示欢迎界面"""
        welcome_text = """
🎬 智能自动化API生成平台
将您的网页操作转化为可重用的Python函数

✨ 核心功能：
• 🎯 录制网页操作流程
• 🤖 AI智能分析参数化
• 🧪 交互式测试验证  
• 📦 生成Python函数代码
"""
        
        console.print(Panel(
            welcome_text,
            title="[bold blue]欢迎使用 Web Automation Platform[/bold blue]",
            border_style="blue",
            padding=(1, 2)
        ))
        
        # 显示配置状态
        config_status = Config.get_ai_config_status()
        console.print(f"🔧 {config_status}", style="dim")
        console.print()
    
    def display_main_menu(self) -> str:
        """显示主菜单并获取用户选择"""
        menu_options = [
            ("1", "🎬 新建录制会话", "录制网页操作并自动生成AI代码"),
            ("2", "📋 管理现有会话", "查看、分析、测试已录制的会话"),
            ("3", "🧪 快速测试", "测试现有会话的自动化函数"),
            ("4", "🚀 生成函数", "将会话转换为Python函数代码"),
            ("5", "⚙️  系统设置", "配置和系统管理"),
            ("6", "❓ 帮助信息", "查看使用帮助"),
            ("0", "👋 退出程序", "退出智能自动化平台")
        ]
        
        # 创建菜单表格
        table = Table(
            title="[bold cyan]主菜单[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
            border_style="cyan",
            title_style="bold cyan"
        )
        table.add_column("选项", style="bold yellow", width=6)
        table.add_column("功能", style="bold white", width=20)
        table.add_column("描述", style="dim", width=35)
        
        for option, title, desc in menu_options:
            table.add_row(option, title, desc)
        
        console.print(table)
        console.print()
        
        choice = Prompt.ask(
            "[bold green]请选择操作[/bold green]",
            choices=["0", "1", "2", "3", "4", "5", "6"],
            default="1"
        )
        return choice
    
    async def handle_new_recording(self):
        """处理新建录制会话"""
        console.print(Panel(
            "[bold blue]🎬 新建录制会话[/bold blue]",
            border_style="blue"
        ))
        
        # 获取会话信息
        session_name = Prompt.ask("📝 输入会话名称", default=f"session_{datetime.now().strftime('%m%d_%H%M')}")
        
        # 📋 获取任务描述 - 这是新增的重要环节！
        console.print(Panel(
            "[bold cyan]📋 任务描述[/bold cyan]\n\n"
            "请详细描述您要完成的任务，这将帮助AI更好地理解您的操作意图：\n\n"
            "💡 示例：\n"
            "• 在百度搜索'Python教程'并获取前3个结果的标题\n"
            "• 登录网站并填写用户信息表单\n"
            "• 从商品页面提取价格和库存信息\n"
            "• 提交订单并获取订单号",
            title="[bold yellow]任务理解[/bold yellow]",
            border_style="cyan"
        ))
        
        task_description = ""
        while not task_description.strip():
            task_description = self._get_multiline_input(
                "🎯 请描述您要完成的任务",
                placeholder="例如：在百度搜索'Python教程'并获取前3个结果的标题..."
            )
            if not task_description.strip():
                console.print("❌ 任务描述不能为空，请详细描述您的操作目标", style="red")
        
        console.print(f"✅ 任务描述: [blue]{task_description}[/blue]")
        
        while True:
            target_url = Prompt.ask("🌐 输入目标网站URL", default="www.baidu.com")
            try:
                # 修复URL格式
                target_url = self._fix_url_format(target_url)
                break
            except Exception as e:
                console.print(f"❌ URL格式错误: {e}", style="red")
                console.print("💡 请输入有效的网站地址，如：www.baidu.com 或 https://example.com")
        
        # 询问是否需要前置登录
        need_prelogin = Confirm.ask("🔐 是否需要先进行登录等前置操作？")
        
        if need_prelogin:
            await self._handle_prelogin_setup(target_url)
        
        # 开始录制
        console.print(f"\n🎬 开始录制会话: [bold cyan]{session_name}[/bold cyan]")
        console.print(f"🌐 目标URL: [blue]{target_url}[/blue]")
        
        if need_prelogin:
            console.print("📋 [yellow]注意：前置登录已完成，现在将开始录制您的业务操作[/yellow]")
        
        console.print(Panel(
            "浏览器即将打开，请在浏览器中执行您要自动化的操作\n"
            "⚠️  只录制业务操作，不要重复登录步骤\n"
            "✅ 操作完成后按 [bold red]Ctrl+C[/bold red] 结束录制",
            title="[bold yellow]录制指引[/bold yellow]",
            border_style="yellow"
        ))
        
        # 等待用户准备
        Prompt.ask("按回车键开始录制", default="")
        
        try:
            recorder = WebRecorder()
            
            # 如果有前置登录，查找最新的认证状态文件
            auth_state_file = None
            if need_prelogin:
                auth_state_file = self._find_latest_auth_state()
                if auth_state_file:
                    console.print(f"🔐 使用认证状态: {auth_state_file.name}", style="blue")
            
            session_id = await recorder.start_recording(
                session_name, 
                target_url, 
                auth_state_file=str(auth_state_file) if auth_state_file else None,
                headless=False  # 录制时显示浏览器，便于用户操作
            )
            
            console.print(f"✅ 录制完成！会话ID: [bold green]{session_id}[/bold green]")
            self.current_session = session_id
            
            # 🎯 获取返回值期望 - 这是新增的重要环节！
            expected_return = await self._get_expected_return_value()
            
            # 保存任务描述和返回值期望到会话数据
            await self._save_task_metadata(session_id, task_description, expected_return)
            
            # 显示任务定义摘要
            console.print(Panel(
                f"🎯 任务定义: [cyan]{task_description}[/cyan]\n"
                f"📎 期望返回: [blue]{expected_return['description']}[/blue] ([yellow]{expected_return['type']}[/yellow])",
                title="[bold green]录制完成[/bold green]",
                border_style="green"
            ))
            
            # 自动进入AI代码生成流程
            console.print("🤖 现在开始AI代码生成...")
            await self._trigger_ai_generation_for_session(
                session_id, task_description, expected_return['description']
            )
                
        except KeyboardInterrupt:
            console.print("\n⏹️  录制已取消")
        except ValueError as e:
            console.print(f"❌ URL错误: {e}", style="red")
            console.print("💡 请检查网址格式是否正确", style="yellow")
        except Exception as e:
            console.print(f"❌ 录制失败: {e}", style="red")
            console.print("💡 常见解决方案：", style="yellow")
            console.print("  • 检查网络连接是否正常")
            console.print("  • 确认目标网站是否可访问")
            console.print("  • 尝试使用完整的URL（包含https://）")
    
    async def _trigger_ai_generation_for_session(
        self, 
        session_id: str, 
        task_description: str, 
        output_format_requirements: str
    ):
        """录制完成后自动触发AI代码生成"""
        session_folder_path = str(Path("sessions") / session_id)
        
        # 询问是否保存生成的函数
        save_function = Confirm.ask("是否将生成的函数保存到文件？", default=True)
        save_path = None
        
        if save_function:
            # 生成默认文件名
            session_name = session_id.replace('session_', '')
            default_path = f"generated_functions/ai_{session_name}.py"
            
            save_path = Prompt.ask(
                "输入保存路径",
                default=default_path
            )
        
        # 开始AI分析
        console.print(Panel(
            f"🤖 开始AI分析和代码生成...\n\n"
            f"会话: [cyan]{session_id}[/cyan]\n"
            f"任务: [blue]{task_description[:50]}{'...' if len(task_description) > 50 else ''}[/blue]\n"
            f"输出: [green]{output_format_requirements[:50]}{'...' if len(output_format_requirements) > 50 else ''}[/green]",
            title="[bold yellow]AI分析中[/bold yellow]",
            border_style="yellow"
        ))
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("AI分析和代码生成中...", total=None)
            
            try:
                # 调用AI分析接口
                result = await self.session_manager.trigger_ai_analysis(
                    session_folder_path=session_folder_path,
                    task_description=task_description,
                    output_format_requirements=output_format_requirements,
                    save_function_path=save_path
                )
                
                progress.update(task, description="分析完成!")
                
                # 显示结果
                if result["success"]:
                    console.print(Panel(
                        f"✅ AI分析完成！\n\n"
                        f"{'📁 已保存到: ' + result['saved_path'] if result['saved_path'] else '💡 代码已生成'}",
                        title="[bold green]成功[/bold green]",
                        border_style="green"
                    ))
                    
                    # 询问是否查看生成的代码
                    if Confirm.ask("是否查看生成的代码？"):
                        from rich.syntax import Syntax
                        code_preview = result["function_code"]
                        if len(code_preview) > 1500:
                            code_preview = code_preview[:1500] + "\n\n... (代码过长，已截断，完整代码请查看保存的文件)"
                        
                        syntax = Syntax(code_preview, "python", theme="monokai", line_numbers=True)
                        console.print(Panel(syntax, title="生成的Python代码"))
                
                else:
                    console.print(Panel(
                        f"❌ AI分析失败\n\n"
                        f"错误信息: {result.get('error', '未知错误')}",
                        title="[bold red]失败[/bold red]",
                        border_style="red"
                    ))
            
            except Exception as e:
                console.print(f"❌ AI分析过程出错: {e}", style="red")
    
    async def _get_expected_return_value(self) -> Dict:
        """获取用户期望的返回值"""
        console.print(Panel(
            "[bold cyan]🎯 返回值设定[/bold cyan]\n\n"
            "请指定您希望这个自动化函数返回什么结果：\n\n"
            "💡 示例：搜索结果的标题列表、商品价格和库存数据、登录成功状态等",
            title="[bold yellow]返回值定义[/bold yellow]",
            border_style="cyan"
        ))
        
        return_description = ""
        while not return_description.strip():
            return_description = self._get_multiline_input(
                "📎 请描述您希望函数返回的内容",
                placeholder="例如：搜索结果的标题列表、商品价格和库存数据..."
            )
            if not return_description.strip():
                console.print("❌ 返回值描述不能为空，请描述您期望的结果", style="red")
        
        # 固定使用字典类型作为返回值
        return_type = "dict"
        
        console.print(f"✅ 返回值设定: [blue]{return_description}[/blue] ([cyan]{return_type}[/cyan])")
        
        return {
            "description": return_description,
            "type": return_type,
            "user_specified": True
        }
    
    async def _save_task_metadata(self, session_id: str, task_description: str, expected_return: Dict):
        """保存任务元数据到会话"""
        try:
            session_dir = Path("sessions") / session_id
            
            # 读取现有的元数据
            metadata_file = session_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = {}
            
            # 添加任务元数据
            metadata["task_definition"] = {
                "description": task_description,
                "expected_return": expected_return,
                "defined_at": datetime.now().isoformat()
            }
            
            # 保存更新后的元数据
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            console.print("💾 任务元数据已保存")
            
        except Exception as e:
            console.print(f"⚠️  保存任务元数据失败: {e}", style="yellow")
    
    async def _handle_prelogin_setup(self, target_url: str):
        """处理前置登录设置"""
        console.print(Panel(
            "🔐 前置登录设置\n\n"
            "即将打开浏览器用于登录，这个过程不会被录制\n\n"
            "🚨 重要说明：\n"
            "• 完成登录后，请 [bold red]关闭浏览器[/bold red]\n"
            "• 关闭浏览器时会自动保存登录状态\n"
            "• 不要在程序中确认，直接关闭浏览器即可",
            title="[bold yellow]登录准备[/bold yellow]",
            border_style="yellow"
        ))
        
        if not Confirm.ask("是否继续打开浏览器进行登录？"):
            console.print("❌ 用户取消前置登录")
            return
        
        # 打开浏览器进行登录（不录制）
        browser = None
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=False)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                console.print(f"🌐 导航到: {target_url}")
                await page.goto(target_url)
                
                console.print(Panel(
                    "🔐 请在浏览器中完成登录\n\n"
                    "完成后请 [bold red]直接关闭浏览器[/bold red]\n"
                    "程序会自动检测并保存登录状态",
                    title="[bold green]登录中...[/bold green]",
                    border_style="green"
                ))
                
                # 等待浏览器被关闭
                await self._wait_for_browser_close(browser, context)
                
        except Exception as e:
            if "browser has been closed" in str(e) or "context has been closed" in str(e):
                console.print("✅ 检测到浏览器已关闭")
                console.print("💾 登录状态已自动保存")
                console.print("✅ 前置登录完成！")
            else:
                console.print(f"❌ 前置登录过程出错: {e}", style="red")
                console.print("💡 这通常不影响录制功能，您可以继续", style="yellow")
    
    async def _wait_for_browser_close(self, browser, context):
        """等待用户关闭浏览器并保存认证状态"""
        import asyncio
        
        try:
            # 监听浏览器关闭事件
            while True:
                try:
                    # 检查浏览器是否仍然连接
                    await asyncio.sleep(1)
                    
                    # 尝试获取浏览器上下文，如果失败说明浏览器已关闭
                    contexts = browser.contexts
                    if not contexts:
                        break
                        
                    # 检查页面是否仍然存在
                    pages = context.pages
                    if not pages:
                        break
                        
                except Exception:
                    # 任何异常都说明浏览器可能已关闭
                    break
            
            # 尝试保存认证状态（如果浏览器还没完全关闭）
            try:
                auth_dir = Path("sessions") / "auth_cache" 
                auth_dir.mkdir(exist_ok=True)
                auth_file = auth_dir / f"auth_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                await context.storage_state(path=str(auth_file))
                console.print(f"💾 登录状态已保存: {auth_file}")
                
            except Exception as save_error:
                # 保存失败通常是因为浏览器已关闭，这是正常的
                console.print("ℹ️  浏览器已关闭，登录状态保存在浏览器缓存中")
                
        except Exception as e:
            # 任何错误都不应该阻止流程继续
            console.print(f"⚠️  监控过程中出现异常: {e}", style="yellow")
        
        finally:
            # 确保浏览器被关闭
            try:
                if browser:
                    await browser.close()
            except:
                pass
    
    def _find_latest_auth_state(self) -> Optional[Path]:
        """查找最新的认证状态文件"""
        auth_dir = Path("sessions") / "auth_cache"
        if not auth_dir.exists():
            return None
        
        auth_files = list(auth_dir.glob("auth_*.json"))
        if not auth_files:
            return None
        
        # 按修改时间排序，返回最新的文件
        latest_file = max(auth_files, key=lambda f: f.stat().st_mtime)
        return latest_file
    
    async def handle_session_management(self):
        """处理会话管理"""
        while True:
            console.print(Panel(
                "[bold blue]📋 会话管理[/bold blue]",
                border_style="blue"
            ))
            
            # 显示会话列表
            sessions = self.session_manager.list_sessions()
            
            if not sessions:
                console.print("📭 [yellow]暂无录制会话[/yellow]")
                if Confirm.ask("是否创建新的录制会话？"):
                    return "new_recording"
                else:
                    return "main_menu"
            
            # 显示会话表格
            table = Table(
                title="录制会话列表",
                show_header=True,
                header_style="bold magenta",
                border_style="blue"
            )
            table.add_column("序号", style="yellow", width=6)
            table.add_column("会话名称", style="bold white", width=20)
            table.add_column("URL", style="blue", width=40)
            table.add_column("创建时间", style="green", width=16)
            table.add_column("状态", style="cyan", width=12)
            
            for i, session in enumerate(sessions, 1):
                status_color = {
                    'analyzed': 'green',
                    'recorded': 'yellow', 
                    'incomplete': 'red',
                    'empty': 'dim'
                }.get(session['status'], 'white')
                
                table.add_row(
                    str(i),
                    session['name'],
                    session['url'][:35] + '...' if len(session['url']) > 35 else session['url'],
                    session['created_at'][:16],
                    f"[{status_color}]{session['status']}[/{status_color}]"
                )
            
            console.print(table)
            console.print()
            
            # 会话操作菜单
            actions = [
                ("分析会话", "🤖"),
                ("测试会话", "🧪"), 
                ("生成函数", "🚀"),
                ("删除会话", "🗑️"),
                ("返回主菜单", "↩️")
            ]
            
            action_table = Table(show_header=False, border_style="dim")
            for i, (action, emoji) in enumerate(actions, 1):
                action_table.add_row(str(i), f"{emoji} {action}")
            
            console.print(action_table)
            
            try:
                session_idx = IntPrompt.ask(
                    "选择要操作的会话序号",
                    default=1,
                    choices=[str(i) for i in range(1, len(sessions) + 1)]
                )
                
                action_idx = IntPrompt.ask(
                    "选择操作",
                    default=1,
                    choices=["1", "2", "3", "4", "5"]
                )
                
                selected_session = sessions[session_idx - 1]
                session_id = selected_session['id']
                
                if action_idx == 1:  # 分析会话
                    await self._analyze_session(session_id)
                elif action_idx == 2:  # 测试会话
                    await self._test_session(session_id)
                elif action_idx == 3:  # 生成函数
                    self._generate_function(session_id, selected_session['name'])
                elif action_idx == 4:  # 删除会话
                    self._delete_session(session_id, selected_session['name'])
                elif action_idx == 5:  # 返回主菜单
                    break
                    
            except ValueError:
                console.print("❌ 无效的选择", style="red")
                continue
    
    async def _analyze_session(self, session_id: str):
        """分析会话"""
        console.print(f"🤖 正在分析会话: [cyan]{session_id}[/cyan]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("AI分析中...", total=None)
            
            try:
                session_data = self.session_manager.load_session(session_id)
                if not session_data:
                    console.print("❌ 会话不存在", style="red")
                    return
                
                result = await self.ai_analyzer.analyze_session(session_data)
                self.session_manager.save_analysis(session_id, result)
                
                progress.update(task, description="分析完成!")
                
                # 显示分析结果
                self._display_analysis_result(result)
                
            except Exception as e:
                console.print(f"❌ 分析失败: {e}", style="red")
    
    async def _test_session(self, session_id: str):
        """测试会话"""
        console.print(f"🧪 测试会话: [cyan]{session_id}[/cyan]")
        
        session_data = self.session_manager.load_session(session_id)
        if not session_data:
            console.print("❌ 会话不存在", style="red")
            return
        
        if not session_data.get('ai_analysis', {}).get('analyzed'):
            console.print("⚠️  会话尚未分析，请先进行AI分析", style="yellow")
            return
        
        # 获取测试参数
        params = self._get_test_parameters(session_data)
        
        try:
            success = await self.cli_interface.test_session(session_id, params)
            if success:
                console.print("✅ 测试成功", style="green")
            else:
                console.print("❌ 测试失败", style="red")
        except Exception as e:
            console.print(f"❌ 测试执行失败: {e}", style="red")
    
    def _get_test_parameters(self, session_data: Dict) -> Dict:
        """获取测试参数"""
        analysis = session_data.get('ai_analysis', {})
        suggested_params = analysis.get('suggested_parameters', [])
        
        if not suggested_params:
            return {}
        
        console.print("📋 请输入测试参数:")
        params = {}
        
        for param in suggested_params:
            param_name = param['name']
            param_type = param.get('type', 'str')
            param_desc = param.get('description', '')
            required = param.get('required', True)
            
            prompt_text = f"{param_name} ({param_desc})"
            if not required:
                prompt_text += " [可选]"
            
            value = Prompt.ask(prompt_text, default="" if not required else None)
            
            if value:
                # 简单的类型转换
                try:
                    if param_type == 'int':
                        params[param_name] = int(value)
                    elif param_type == 'bool':
                        params[param_name] = value.lower() in ('true', '1', 'yes', 'y')
                    else:
                        params[param_name] = value
                except ValueError:
                    params[param_name] = value  # 转换失败时保持字符串
        
        return params
    
    def _generate_function(self, session_id: str, session_name: str):
        """生成函数"""
        console.print(f"🚀 生成函数: [cyan]{session_id}[/cyan]")
        
        try:
            function_code = self.session_manager.generate_function(session_id)
            
            # 生成输出文件名
            clean_name = session_name.replace(' ', '_').replace('-', '_').lower()
            output_file = f"generated_functions/{clean_name}.py"
            
            Path("generated_functions").mkdir(exist_ok=True)
            Path(output_file).write_text(function_code, encoding='utf-8')
            
            console.print(f"✅ 函数已生成: [bold green]{output_file}[/bold green]")
            
            # 询问是否查看代码
            if Confirm.ask("是否查看生成的代码？"):
                from rich.syntax import Syntax
                syntax = Syntax(function_code[:1000] + "\n..." if len(function_code) > 1000 else function_code, 
                              "python", theme="monokai", line_numbers=True)
                console.print(Panel(syntax, title="生成的Python代码"))
            
        except Exception as e:
            console.print(f"❌ 函数生成失败: {e}", style="red")
    
    def _delete_session(self, session_id: str, session_name: str):
        """删除会话"""
        if Confirm.ask(f"确定要删除会话 '{session_name}' 吗？", default=False):
            if self.session_manager.delete_session(session_id):
                console.print(f"✅ 会话 [red]{session_name}[/red] 已删除")
            else:
                console.print("❌ 删除失败", style="red")
    
    def _display_analysis_result(self, result: Dict):
        """显示分析结果"""
        console.print(Panel(
            "[bold green]🎉 AI分析完成![/bold green]",
            border_style="green"
        ))
        
        # 显示参数表
        if 'suggested_parameters' in result and result['suggested_parameters']:
            param_table = Table(
                title="🔍 识别的参数",
                show_header=True,
                header_style="bold cyan",
                border_style="cyan"
            )
            param_table.add_column("参数名", style="bold yellow")
            param_table.add_column("类型", style="blue")
            param_table.add_column("描述", style="white")
            param_table.add_column("必需", style="green")
            
            for param in result['suggested_parameters']:
                required = "✅" if param.get('required', True) else "⭕"
                param_table.add_row(
                    param['name'],
                    param.get('type', 'str'),
                    param.get('description', ''),
                    required
                )
            
            console.print(param_table)
        
        # 显示返回值提取信息
        if 'return_extraction' in result:
            return_info = result['return_extraction']
            console.print(f"\n🎯 返回值提取:")
            
            return_table = Table(
                show_header=False,
                border_style="green",
                box=None
            )
            return_table.add_column("Label", style="bold cyan")
            return_table.add_column("Value", style="white")
            
            return_table.add_row("📦 描述:", return_info.get('description', '未指定'))
            return_table.add_row("🔧 提取方法:", return_info.get('method', 'text'))
            
            elements = return_info.get('elements', [])
            if elements:
                elements_str = ', '.join(elements[:3])  # 只显示前3个
                if len(elements) > 3:
                    elements_str += f' +{len(elements) - 3}个...' 
                return_table.add_row("🎯 目标元素:", elements_str)
            
            console.print(return_table)
        
        # 显示函数签名
        if 'function_signature' in result:
            console.print(f"\n📝 函数签名:")
            from rich.syntax import Syntax
            syntax = Syntax(result['function_signature'], "python", theme="monokai")
            console.print(syntax)
        
        # 显示函数描述
        if 'function_description' in result:
            console.print(f"\n📄 函数描述:")
            console.print(f"[dim]{result['function_description']}[/dim]")
    
    async def handle_quick_test(self):
        """处理快速测试功能"""
        console.print(Panel(
            "[bold blue]🧪 快速测试[/bold blue]",
            border_style="blue"
        ))
        
        # 检查是否有可用的生成函数
        generated_functions_dir = Path("generated_functions")
        if not generated_functions_dir.exists():
            console.print("📭 [yellow]暂无生成的函数可供测试[/yellow]")
            if Confirm.ask("是否先创建一个录制会话？"):
                return "new_recording"
            else:
                return "main_menu"
        
        # 获取所有Python函数文件
        function_files = list(generated_functions_dir.glob("*.py"))
        if not function_files:
            console.print("📭 [yellow]generated_functions 目录中暂无Python函数文件[/yellow]")
            if Confirm.ask("是否先创建一个录制会话？"):
                return "new_recording"
            else:
                return "main_menu"
        
        # 显示可用函数列表
        console.print("\n📂 可用的函数文件:")
        table = Table(
            show_header=True,
            header_style="bold magenta",
            border_style="blue"
        )
        table.add_column("序号", style="yellow", width=6)
        table.add_column("文件名", style="bold white", width=30)
        table.add_column("修改时间", style="green", width=16)
        table.add_column("大小", style="cyan", width=10)
        
        for i, func_file in enumerate(function_files, 1):
            stat = func_file.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            file_size = f"{stat.st_size} bytes"
            
            table.add_row(
                str(i),
                func_file.name,
                modified_time,
                file_size
            )
        
        console.print(table)
        console.print()
        
        try:
            # 选择函数文件
            file_idx = IntPrompt.ask(
                "选择要测试的函数文件",
                default=1,
                choices=[str(i) for i in range(1, len(function_files) + 1)]
            )
            
            selected_file = function_files[file_idx - 1]
            console.print(f"✅ 选择了文件: [cyan]{selected_file.name}[/cyan]")
            
            # 读取函数代码并分析参数
            function_code = selected_file.read_text(encoding='utf-8')
            function_params = await self._extract_function_parameters(function_code)
            
            # 显示函数注释/文档
            docstring = self._extract_function_docstring(function_code)
            if docstring:
                console.print(Panel(
                    docstring,
                    title="[bold blue]📄 函数说明[/bold blue]",
                    border_style="blue",
                    padding=(1, 2)
                ))
                console.print()
            
            if function_params:
                console.print("\n📋 请输入测试参数:")
                test_params = {}
                
                for param_name, param_info in function_params.items():
                    param_type = param_info.get('type', 'str')
                    param_desc = param_info.get('description', '')
                    required = param_info.get('required', True)
                    default_value = param_info.get('default')
                    
                    prompt_text = f"{param_name}"
                    if param_desc:
                        prompt_text += f" ({param_desc})"
                    if param_type != 'str':
                        prompt_text += f" [{param_type}]"
                    if not required:
                        prompt_text += " [可选]"
                    
                    if default_value is not None:
                        value = Prompt.ask(prompt_text, default=str(default_value))
                    elif not required:
                        value = Prompt.ask(prompt_text, default="")
                    else:
                        value = Prompt.ask(prompt_text)
                    
                    # 类型转换
                    if value:
                        try:
                            if param_type == 'int':
                                test_params[param_name] = int(value)
                            elif param_type == 'bool':
                                test_params[param_name] = value.lower() in ('true', '1', 'yes', 'y')
                            elif param_type == 'float':
                                test_params[param_name] = float(value)
                            else:
                                test_params[param_name] = value
                        except ValueError:
                            test_params[param_name] = value  # 转换失败时保持字符串
            else:
                console.print("ℹ️  未检测到函数参数，将以无参数方式执行")
                test_params = {}
            
            # 执行测试前再次显示函数信息
            console.print(f"\n🚀 开始测试函数...")
            console.print(f"📁 函数文件: {selected_file.name}")
            
            # 再次显示函数说明（避免被进度条清除）
            if docstring:
                console.print(Panel(
                    docstring,
                    title="[bold blue]📄 函数说明[/bold blue]",
                    border_style="blue",
                    padding=(1, 2)
                ))
            
            console.print(f"📋 测试参数: {test_params}")
            console.print()
            
            # 使用FunctionExecutor执行测试
            executor = self.session_manager.get_executor()
            
            # 显示简单的进度指示器（不使用动态刷新）
            console.print("⏳ 执行函数测试中...", style="yellow")
            
            try:
                # 生成测试会话名称
                test_session_name = f"quicktest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                test_output_dir = f"./test_results/{test_session_name}"
                
                result = await executor.execute_with_recording(
                    function_code=function_code,
                    function_params=test_params,
                    recording_output_dir=test_output_dir,
                    session_name=test_session_name
                )
                
                console.print("✅ 测试完成!", style="green")
                
                # 测试完成后再次显示函数信息和参数
                console.print(Panel(
                    f"📁 函数文件: {selected_file.name}\n"
                    f"📋 测试参数: {test_params}\n\n"
                    f"📄 函数说明:\n{docstring}" if docstring else f"📁 函数文件: {selected_file.name}\n📋 测试参数: {test_params}",
                    title="[bold blue]🧪 测试信息[/bold blue]",
                    border_style="blue",
                    padding=(1, 2)
                ))
                
                # 显示测试结果
                if result["success"]:
                    console.print(Panel(
                        f"✅ 函数测试成功！\n\n"
                        f"⏱️  执行时间: {result['execution_time']:.2f}秒\n"
                        f"📊 执行结果: {result['execution_result']}\n"
                        f"📁 录制数据: {result['recording_session_path']}",
                        title="[bold green]测试成功[/bold green]",
                        border_style="green"
                    ))
                    
                    # 询问是否查看详细结果
                    if Confirm.ask("是否查看详细的执行结果？"):
                        from rich.syntax import Syntax
                        result_json = json.dumps(result['execution_result'], ensure_ascii=False, indent=2)
                        syntax = Syntax(result_json, "json", theme="monokai", line_numbers=True)
                        console.print(Panel(syntax, title="详细执行结果"))
                
                else:
                    console.print(Panel(
                        f"❌ 函数测试失败\n\n"
                        f"❌ 错误信息: {result.get('error', '未知错误')}\n"
                        f"⏱️  执行时间: {result['execution_time']:.2f}秒",
                        title="[bold red]测试失败[/bold red]",
                        border_style="red"
                    ))
                
            except Exception as e:
                console.print(f"❌ 测试执行过程出错: {e}", style="red")
                
        except ValueError:
            console.print("❌ 无效的选择", style="red")
    
    async def _extract_function_parameters(self, function_code: str) -> Dict[str, Dict]:
        """从函数代码中提取参数信息"""
        import re
        import ast
        
        params = {}
        
        try:
            # 解析Python代码
            tree = ast.parse(function_code)
            
            # 查找async def函数
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                    # 跳过私有函数和特殊函数
                    if node.name.startswith('_') or node.name.endswith('_sync'):
                        continue
                    
                    # 提取函数参数
                    for arg in node.args.args:
                        if arg.arg == 'self':  # 跳过self参数
                            continue
                        
                        param_info = {
                            'type': 'str',  # 默认类型
                            'required': True,
                            'description': '',
                            'default': None
                        }
                        
                        # 尝试从类型注解获取类型
                        if arg.annotation:
                            if isinstance(arg.annotation, ast.Name):
                                param_info['type'] = arg.annotation.id
                            elif isinstance(arg.annotation, ast.Constant):
                                param_info['type'] = str(arg.annotation.value)
                        
                        params[arg.arg] = param_info
                    
                    # 处理默认参数
                    if node.args.defaults:
                        defaults_count = len(node.args.defaults)
                        args_count = len(node.args.args)
                        
                        for i, default in enumerate(node.args.defaults):
                            arg_index = args_count - defaults_count + i
                            if arg_index < len(node.args.args):
                                arg_name = node.args.args[arg_index].arg
                                if arg_name in params:
                                    params[arg_name]['required'] = False
                                    if isinstance(default, ast.Constant):
                                        params[arg_name]['default'] = default.value
                    
                    # 只处理第一个找到的函数
                    break
            
            # 尝试从docstring提取参数描述
            docstring_match = re.search(r'"""(.*?)"""', function_code, re.DOTALL)
            if docstring_match:
                docstring = docstring_match.group(1)
                
                # 查找Args部分
                args_match = re.search(r'Args:(.*?)(?:Returns:|$)', docstring, re.DOTALL | re.IGNORECASE)
                if args_match:
                    args_section = args_match.group(1)
                    
                    # 提取每个参数的描述
                    for param_name in params.keys():
                        param_match = re.search(rf'{param_name}[:\s]*([^:\n]*)', args_section)
                        if param_match:
                            params[param_name]['description'] = param_match.group(1).strip()
        
        except Exception as e:
            console.print(f"⚠️  解析函数参数时出错: {e}", style="yellow")
        
        return params
    
    def _extract_function_docstring(self, function_code: str) -> str:
        """从函数代码中提取docstring"""
        import re
        import ast
        
        try:
            # 解析Python代码
            tree = ast.parse(function_code)
            
            # 查找async def函数
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                    # 跳过私有函数和特殊函数
                    if node.name.startswith('_') or node.name.endswith('_sync'):
                        continue
                    
                    # 获取函数的第一个语句
                    if (node.body and 
                        isinstance(node.body[0], ast.Expr) and 
                        isinstance(node.body[0].value, ast.Constant) and 
                        isinstance(node.body[0].value.value, str)):
                        return node.body[0].value.value.strip()
                    
                    # 如果AST方法失败，尝试正则表达式
                    break
            
            # 备用方法：使用正则表达式提取docstring
            docstring_match = re.search(r'"""(.*?)"""', function_code, re.DOTALL)
            if docstring_match:
                return docstring_match.group(1).strip()
            
            # 尝试单引号docstring
            docstring_match = re.search(r"'''(.*?)'''", function_code, re.DOTALL)
            if docstring_match:
                return docstring_match.group(1).strip()
                
        except Exception as e:
            console.print(f"⚠️  解析函数docstring时出错: {e}", style="yellow")
        
        return ""
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
[bold cyan]🎬 智能自动化API生成平台 - 使用指南[/bold cyan]

[bold yellow]📋 一键录制生成流程：[/bold yellow]
1. [green]选择"新建录制会话"[/green] - 输入任务描述和期望返回值
2. [blue]在浏览器中执行操作[/blue] - 系统自动记录您的操作
3. [yellow]AI自动生成代码[/yellow] - 录制完成后立即生成可执行函数
4. [magenta]保存和使用代码[/magenta] - 获得完整的Python自动化函数

[bold yellow]💡 录制技巧：[/bold yellow]
• 录制前详细描述任务目标，AI会生成更准确的代码
• 如果需要登录，选择"前置登录"选项避免重复录制
• 录制时专注于核心业务逻辑
• 明确描述期望的返回数据格式

[bold yellow]🤖 AI代码生成：[/bold yellow]
• AI会基于您的任务描述自动生成可执行函数
• 支持参数化处理，您的输入值会被自动识别为参数
• 生成的代码包含完整的错误处理和文档
• 可以对现有会话重新进行AI分析优化

[bold yellow]📁 文件输出：[/bold yellow]
• 生成的函数保存在 generated_functions/ 目录
• 每个函数都是独立可执行的Python文件
• 支持同步和异步两种调用方式
• 包含使用示例和完整文档

[bold yellow]🔧 高级功能：[/bold yellow]
• 会话管理：查看和管理所有录制会话
• 函数测试：验证生成函数的执行效果
• 系统设置：配置AI模型和系统参数

[dim]更多信息请查看项目README.md文件[/dim]
"""
        
        console.print(Panel(help_text, border_style="cyan", padding=(1, 2)))
    
    def _fix_url_format(self, url: str) -> str:
        """修复URL格式"""
        if not url or not url.strip():
            raise ValueError("URL不能为空")
        
        # 去除前后空格
        url = url.strip()
        
        # 基本格式验证
        if ' ' in url:
            raise ValueError("URL不能包含空格")
        
        # 如果URL不以http://或https://开头，默认添加https://
        if not url.startswith(('http://', 'https://')):
            original_url = url
            url = 'https://' + url
            console.print(f"🔧 自动添加协议: [dim]{original_url}[/dim] → [blue]{url}[/blue]")
        else:
            console.print(f"✅ URL格式正确: [blue]{url}[/blue]")
        
        return url
    
    def _get_multiline_input(self, prompt_text: str, placeholder: str = "") -> str:
        """获取多行文本输入，支持编辑和光标移动"""
        from rich.panel import Panel
        
        # 统一宽度设置 - 与输入框完全一致（占满控制台宽度）
        PANEL_WIDTH = console.size.width
        
        # 显示美观的输入界面提示
        console.print()
        
        return self._get_enhanced_input()
    
    def _get_enhanced_input(self) -> str:
        """增强的输入体验，让用户在框架内部输入"""
        import sys
        from rich.text import Text
        
        # 统一宽度设置 - 确保与Panel完全一致（占满控制台宽度）
        TOTAL_WIDTH = console.size.width  # 总显示宽度
        BOX_WIDTH = TOTAL_WIDTH - 2  # 减去左右边框，76字符内容
        PANEL_WIDTH = TOTAL_WIDTH  # Panel使用相同总宽度
        
        lines = []
        
        # 绘制输入框顶部
        console.print()
        console.print("╭" + "─" * BOX_WIDTH + "╮")
        
        try:
            # 设置readline支持
            if sys.platform != 'win32':
                try:
                    import readline
                    readline.parse_and_bind('tab: complete')
                    readline.parse_and_bind('set editing-mode emacs')
                except ImportError:
                    pass
            
            line_count = 0
            while True:
                try:
                    line_count += 1
                    
                    # 输入提示符 - 在框架内显示（与期望样式一致）
                    if line_count == 1:
                        prompt_line = "│ > "
                    else:
                        prompt_line = "│   "

                    # 先输出提示符，不换行；在同一行右侧补齐空格并画右边框，然后在下一行临时绘制底边线，最后恢复光标到提示符处
                    sys.stdout.write(prompt_line)
                    sys.stdout.flush()
                    # 右侧边框（保持本行封闭）
                    prompt_visible_len = Text(prompt_line).cell_len
                    right_fill = max(0, BOX_WIDTH - prompt_visible_len)
                    sys.stdout.write("\x1b[s")  # save cursor at input start
                    sys.stdout.write(" " * right_fill + "│")
                    sys.stdout.write("\x1b[u")  # restore to after prompt
                    sys.stdout.flush()
                    # 保存光标，绘制底边线，再恢复
                    sys.stdout.write("\x1b[s")  # save cursor
                    sys.stdout.write("\n")
                    sys.stdout.write("╰" + "─" * BOX_WIDTH + "╯")
                    sys.stdout.write("\x1b[u")  # restore cursor
                    sys.stdout.flush()

                    # 获取用户输入（不再重复打印提示）
                    line = input("")
                    
                    # 空行结束输入
                    if line.strip() == "" and lines:
                        done_text = Text.from_markup("[green]✅ 输入完成[/green]")
                        # 与期望样式：在新的一行左对齐显示完成，不额外缩进，并保持右边框
                        done_len = done_text.cell_len
                        done_pad = max(0, BOX_WIDTH - done_len)
                        console.print("│", done_text, " " * done_pad, "│", sep="")
                        break
                    
                    # 第一行空行继续等待
                    if line.strip() == "" and not lines:
                        line_count -= 1  # 不计数
                        warn_text = Text.from_markup("[yellow]⚠️ 请输入内容...[/yellow]")
                        warn_len = warn_text.cell_len
                        warn_pad = max(0, BOX_WIDTH - warn_len)
                        console.print("│", warn_text, " " * warn_pad, "│", sep="")
                        continue
                    
                    lines.append(line)
                    
                    # 同框展示：不输出统计信息，保持输入区域简洁
                    
                except KeyboardInterrupt:
                    cancel_text = Text.from_markup("[red]❌ 用户取消输入[/red]")
                    cancel_len = cancel_text.cell_len
                    cancel_pad = max(0, BOX_WIDTH - cancel_len)
                    console.print("│", cancel_text, " " * cancel_pad, "│", sep="")
                    console.print("│" + " " * BOX_WIDTH + "│")
                    console.print("╰" + "─" * BOX_WIDTH + "╯")
                    return ""
                except EOFError:
                    eof_text = Text.from_markup("[blue]✅ Ctrl+D 结束输入[/blue]")
                    eof_len = eof_text.cell_len
                    eof_pad = max(0, BOX_WIDTH - eof_len)
                    console.print("│", eof_text, " " * eof_pad, "│", sep="")
                    console.print("│" + " " * BOX_WIDTH + "│")
                    break
        
        except Exception as e:
            error_msg = str(e)[:40] + "..." if len(str(e)) > 40 else str(e)
            err_text = Text.from_markup("  [red]❌ 错误: " + error_msg + "[/red]")
            err_len = err_text.cell_len
            err_pad = max(0, BOX_WIDTH - err_len)
            console.print("│", err_text, " " * err_pad, "│", sep="")
            console.print("│" + " " * BOX_WIDTH + "│")
            console.print("╰" + "─" * BOX_WIDTH + "╯")
            return ""
        
        # 绘制底部边框 - 关键修复！
        console.print("╰" + "─" * BOX_WIDTH + "╯")
        
        result = "\n".join(lines).strip()
        
        # 同框展示：不再弹出额外结果面板
        
        return result
    
    
    def show_system_settings(self):
        """显示系统设置"""
        console.print(Panel(
            "[bold blue]⚙️  系统设置[/bold blue]",
            border_style="blue"
        ))
        
        # 显示当前配置
        config_table = Table(
            title="当前配置",
            show_header=True,
            header_style="bold magenta",
            border_style="blue"
        )
        config_table.add_column("配置项", style="yellow")
        config_table.add_column("值", style="white")
        
        config_table.add_row("API_KEY", f"{Config.API_KEY[:10]}..." if Config.API_KEY else "未设置")
        config_table.add_row("BASE_URL", Config.BASE_URL or "默认")
        config_table.add_row("MODEL_NAME", Config.MODEL_NAME)
        config_table.add_row("浏览器", Config.DEFAULT_BROWSER)
        config_table.add_row("会话目录", Config.SESSIONS_DIR)
        
        console.print(config_table)
        
        console.print(f"\n🔧 配置状态: {Config.get_ai_config_status()}")
        console.print("\n💡 如需修改配置，请编辑 .env 文件")
    
    async def run(self):
        """运行交互式CLI"""
        self.display_welcome()
        
        while True:
            try:
                choice = self.display_main_menu()
                
                if choice == "0":  # 退出
                    console.print("👋 [bold blue]感谢使用智能自动化平台！[/bold blue]")
                    break
                elif choice == "1":  # 新建录制
                    await self.handle_new_recording()
                elif choice == "2":  # 管理会话
                    await self.handle_session_management()
                elif choice == "3":  # 快速测试
                    await self.handle_quick_test()
                elif choice == "4":  # 生成函数
                    console.print("🚀 批量生成功能开发中...")
                elif choice == "5":  # 系统设置
                    self.show_system_settings()
                elif choice == "6":  # 帮助
                    self.show_help()
                
                # 等待用户按键继续
                if choice != "0":
                    console.print()
                    Prompt.ask("[dim]按回车键继续...[/dim]", default="")
                    console.clear()
                    
            except KeyboardInterrupt:
                console.print("\n👋 [yellow]程序已退出[/yellow]")
                break
            except Exception as e:
                console.print(f"\n❌ 发生错误: {e}", style="red")
                console.print("[dim]按回车键继续...[/dim]")
                input()

# 启动交互式CLI的便捷函数
async def start_interactive_cli():
    """启动交互式CLI"""
    cli = InteractiveCLI()
    await cli.run()

if __name__ == "__main__":
    asyncio.run(start_interactive_cli())