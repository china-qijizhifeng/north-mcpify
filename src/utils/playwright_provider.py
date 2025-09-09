"""
Playwright实例提供器
提供统一的Playwright实例获取接口，支持可选的录制功能
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from rich.console import Console


console = Console()

class PlaywrightProvider:
    """Playwright实例提供器"""
    
    def __init__(self):
        self._active_sessions = {}  # 跟踪活跃的录制会话
        self._recorders = {}  # session_name -> WebRecorder
    
    async def get_playwright_instance(
        self,
        enable_recording: bool = True,
        session_name: str = "ai_execution",
        recording_output_dir: Optional[str] = None,
        session_path: Optional[str] = None,
        auth_state_file: Optional[str] = None,
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None
    ) -> Tuple[Browser, BrowserContext, Page]:
        """
        获取Playwright实例
        
        Args:
            enable_recording: 是否启用录制功能
            session_name: 录制会话名称
            recording_output_dir: 录制输出目录，如果为None则使用默认位置
            session_path: 完整的会话路径，如果指定则直接使用这个路径（优先级高于其他路径参数）
            auth_state_file: 认证状态文件路径，用于复用之前的登录状态
            headless: 是否以无头模式运行
            viewport: 视口大小，如 {"width": 1920, "height": 1080}
            
        Returns:
            Tuple[Browser, BrowserContext, Page]: 浏览器、上下文、页面实例
        """
        if enable_recording:
            return await self._get_recording_instance(
                session_name, recording_output_dir, session_path, auth_state_file, headless, viewport
            )
        else:
            return await self._get_normal_instance(headless, viewport, auth_state_file)
    
    async def _get_recording_instance(
        self,
        session_name: str,
        recording_output_dir: Optional[str],
        session_path: Optional[str],
        auth_state_file: Optional[str],
        headless: bool,
        viewport: Optional[Dict[str, int]]
    ) -> Tuple[Browser, BrowserContext, Page]:
        """获取带录制功能的Playwright实例"""
        console.print(f"🎬 启动录制模式: {session_name}")
        
        # 处理session_path逻辑
        if session_path:
            # 如果指定了完整路径，直接使用
            console.print(f"📁 使用指定路径: {session_path}")
            # 从路径中提取session名称，如果用户没有明确指定的话
            if session_name == "ai_execution":  # 默认值，用路径名替代
                unique_session_name = Path(session_path).name
                console.print(f"📝 使用路径名作为session名称: {unique_session_name}")
            else:
                unique_session_name = session_name  # 用户明确指定的
            session_dir = session_path
        else:
            # 生成唯一的会话名称和路径
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_session_name = f"{session_name}_{timestamp}"
            session_dir = None  # 让WebRecorder使用默认逻辑
        
        try:
            # 延迟导入避免循环导入
            from src.recording.recorder import WebRecorder
            
            # 创建新的WebRecorder实例
            recorder = WebRecorder()
            
            # 初始化WebRecorder进行录制（非阻塞）
            session_id = await recorder.initialize_recording(
                unique_session_name,
                "https://example.com",  # 占位URL，实际URL由用户代码控制
                output_dir=recording_output_dir or 'sessions',
                custom_session_path=session_path,
                auth_state_file=auth_state_file,
                headless=headless,
                viewport=viewport
            )
            
            console.print(f"📋 录制会话已启动: {session_id}")
            
            # 获取录制器的浏览器实例
            browser = recorder.browser
            context = recorder.context
            page = recorder.page
            
            # 视口大小已经在创建context时设置，无需在这里再设置
            
            # 记录会话信息，便于后续清理和数据获取
            session_info = {
                "session_id": session_id,
                "recording_output_dir": recording_output_dir,
                "recorder": recorder,
                "started_at": datetime.now()
            }
            self._active_sessions[unique_session_name] = session_info
            self._recorders[unique_session_name] = recorder
            
            console.print(f"✅ 录制实例已准备就绪")
            
            # 为页面对象添加录制方法（如果启用了录制）
            if hasattr(recorder, 'record_programmatic_action'):
                # 创建包装函数来记录操作
                original_click = page.click
                original_fill = page.fill
                original_goto = page.goto
                
                async def recorded_click(selector, **kwargs):
                    result = await original_click(selector, **kwargs)
                    await recorder.record_programmatic_action('click', selector)
                    return result
                
                async def recorded_fill(selector, value, **kwargs):
                    result = await original_fill(selector, value, **kwargs)
                    await recorder.record_programmatic_action('input', selector, value)
                    return result
                
                async def recorded_goto(url, **kwargs):
                    result = await original_goto(url, **kwargs)
                    await recorder.record_programmatic_action('navigation', 'page', url)
                    return result
                
                # 替换原始方法
                page.click = recorded_click
                page.fill = recorded_fill
                page.goto = recorded_goto
                
                console.print("✅ 页面方法已包装为录制版本")
            
            return browser, context, page
            
        except Exception as e:
            console.print(f"❌ 启动录制模式失败: {e}", style="red")
            console.print("🔄 回退到普通模式...")
            return await self._get_normal_instance(headless, viewport, auth_state_file)
    
    async def _get_normal_instance(
        self,
        headless: bool,
        viewport: Optional[Dict[str, int]],
        auth_state_file: Optional[str] = None
    ) -> Tuple[Browser, BrowserContext, Page]:
        """获取普通的Playwright实例"""
        console.print("🌐 启动普通模式")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        
        context_options = {}
        if viewport:
            context_options['viewport'] = viewport
        else:
            context_options['viewport'] = {'width': 1920, 'height': 1080}
            
        # 如果提供了认证状态文件，加载它
        if auth_state_file:
            from pathlib import Path
            auth_path = Path(auth_state_file)
            if auth_path.exists():
                context_options['storage_state'] = str(auth_path)
                console.print(f"🔐 加载认证状态: {auth_state_file}")
            else:
                console.print(f"⚠️ 认证状态文件不存在: {auth_state_file}", style="yellow")
        
        context = await browser.new_context(**context_options)
        page = await context.new_page()
        
        console.print("✅ 普通实例已准备就绪")
        return browser, context, page
    
    async def finalize_recording(
        self,
        session_name: str,
        custom_output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        完成录制并获取录制数据
        
        Args:
            session_name: 会话名称（不含时间戳的原始名称）
            custom_output_dir: 自定义输出目录
            
        Returns:
            Dict: 包含录制数据路径、截图、HTML等信息
        """
        # 找到匹配的活跃会话
        matching_session = None
        session_key = None
        
        for key, session_info in self._active_sessions.items():
            if key.startswith(session_name):
                matching_session = session_info
                session_key = key
                break
        
        if not matching_session:
            console.print(f"⚠️ 未找到活跃的录制会话: {session_name}", style="yellow")
            return {
                "success": False,
                "error": "未找到匹配的录制会话"
            }
        
        try:
            session_id = matching_session["session_id"]
            recorder = matching_session["recorder"]
            
            console.print(f"🏁 完成录制会话: {session_id}")
            
            # 程序化停止录制并保存数据
            recorder.stop_recording()
            
            # 获取会话路径并保存数据
            sessions_dir = recorder.session_dir
            await recorder.finalize_and_save(sessions_dir, session_name, "programmatic")
            
            # 获取最终状态数据
            final_screenshot = None
            final_html = None
            
            if sessions_dir.exists():
                # 查找最终截图
                screenshot_dir = sessions_dir / "screenshots"
                if screenshot_dir.exists():
                    screenshots = list(screenshot_dir.glob("*.png"))
                    if screenshots:
                        final_screenshot = str(max(screenshots, key=lambda p: p.stat().st_mtime))
                
                # 查找最终HTML
                html_dir = sessions_dir / "html_snapshots"
                if html_dir.exists():
                    html_files = list(html_dir.glob("*.html"))
                    if html_files:
                        latest_html = max(html_files, key=lambda p: p.stat().st_mtime)
                        final_html = latest_html.read_text(encoding='utf-8')
            
            # 如果指定了自定义输出目录，复制数据
            final_output_dir = str(sessions_dir)
            if custom_output_dir and sessions_dir.exists():
                import shutil
                output_path = Path(custom_output_dir)
                if output_path.exists():
                    shutil.rmtree(output_path)
                shutil.copytree(sessions_dir, output_path)
                final_output_dir = str(output_path)
                console.print(f"📁 录制数据已复制到: {output_path}")
            
            # 清理会话记录
            if session_key in self._active_sessions:
                del self._active_sessions[session_key]
            
            return {
                "success": True,
                "session_id": session_id,
                "recording_path": final_output_dir,
                "final_screenshot": final_screenshot,
                "final_html": final_html,
                "sessions_dir": str(sessions_dir)
            }
            
        except Exception as e:
            console.print(f"❌ 完成录制时出错: {e}", style="red")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_active_sessions(self) -> Dict[str, Dict]:
        """获取所有活跃的录制会话"""
        return self._active_sessions.copy()


# 全局实例，便于用户直接导入使用
_provider_instance = PlaywrightProvider()

async def get_playwright_instance(
    enable_recording: bool = True,
    session_name: str = "ai_execution", 
    recording_output_dir: Optional[str] = None,
    session_path: Optional[str] = None,
    auth_state_file: Optional[str] = None,
    headless: bool = True,
    viewport: Optional[Dict[str, int]] = None
) -> Tuple[Browser, BrowserContext, Page]:
    """
    获取Playwright实例的便捷函数
    
    用户可以直接导入这个函数：
    from src.utils.playwright_provider import get_playwright_instance
    
    Args:
        enable_recording: 是否启用录制功能
        session_name: 录制会话名称
        recording_output_dir: 录制输出目录
        headless: 是否以无头模式运行
        viewport: 视口大小
        
    Returns:
        Tuple[Browser, BrowserContext, Page]: 浏览器、上下文、页面实例
    """
    return await _provider_instance.get_playwright_instance(
        enable_recording=enable_recording,
        session_name=session_name,
        recording_output_dir=recording_output_dir,
        session_path=session_path,
        auth_state_file=auth_state_file,
        headless=headless,
        viewport=viewport
    )

async def finalize_recording(
    session_name: str,
    custom_output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    完成录制并获取录制数据的便捷函数
    
    Args:
        session_name: 会话名称
        custom_output_dir: 自定义输出目录
        
    Returns:
        Dict: 录制结果信息
    """
    return await _provider_instance.finalize_recording(session_name, custom_output_dir)