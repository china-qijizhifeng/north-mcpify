"""
网页操作录制引擎
使用Playwright进行浏览器自动化和操作录制
"""

import asyncio
import json
import time
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from rich.console import Console

from src.utils.context_capturer import ContextCapturer
from src.utils.event_listener import EventListener

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    Message,
    ResultMessage,
    SystemMessage,
    UserMessage,
    query,
)

console = Console()

class WebRecorder:
    """网页操作录制器"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_id: Optional[str] = None
        self.session_dir: Optional[Path] = None  # 添加session_dir属性
        self.operations: List[Dict] = []
        self.context_capturer = ContextCapturer()
        self.event_listener = EventListener()
        self.cached_page_title: str = ''  # 缓存页面标题
        self.recording_interrupted: bool = False  # 标记录制是否被中断
        
        # HTML动态保存相关
        self.html_cache = {}  # URL -> HTML内容映射
        self.url_timeline = []  # URL访问时间线
        self.html_monitor_task = None
        
        # 输入事件去重相关
        self.pending_input_operations = {}  # selector -> operation_data 缓存连续输入
        self.input_merge_delay = 1.0  # 1秒内的连续输入会被合并
        # 记录每个选择器最近一次已保存的输入操作（用于后续替换）
        self.last_input_by_selector: Dict[str, Dict[str, Any]] = {}
        
        # 元素选择相关
        self.element_selection_mode = False
        self.selected_element = None
        
        # 操作记录序列化锁，防止并发录制操作相互干扰
        self._record_operation_semaphore = asyncio.Semaphore(1)
        
        # 程序化停止录制的标志
        self.stop_recording_flag = False
        
    async def start_recording(
        self, 
        name: str, 
        url: str, 
        output_dir: str = 'sessions', 
        auth_state_file: Optional[str] = None,
        headless: bool = False
    ) -> str:
        """开始录制会话"""
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_dir = Path(output_dir) / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存会话目录路径供后续使用
        self.session_dir = session_dir
        
        # 创建截图目录
        screenshots_dir = session_dir / 'screenshots'
        screenshots_dir.mkdir(exist_ok=True)
        
        console.print(f"📁 会话目录: {session_dir}")
        console.print("🎬 启动浏览器录制...")
        
        # 验证URL格式
        url = self._validate_url(url)
        
        async with async_playwright() as playwright:
            # 启动浏览器
            self.browser = await playwright.chromium.launch(
                headless=headless,
                slow_mo=1000,  # 减慢操作以便观察
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            
            # 创建上下文（使用认证状态如果提供了）
            context_kwargs = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            if auth_state_file and Path(auth_state_file).exists():
                context_kwargs['storage_state'] = auth_state_file
                console.print(f"🔐 使用认证状态: {auth_state_file}", style="blue")
            
            self.context = await self.browser.new_context(**context_kwargs)
            
            # 在context级别注入JavaScript事件监听器
            await self.context.add_init_script("""
        console.log('[WebAutomation] Context级别初始化事件监听器');
        
            // 增强持久性：防止页面脚本意外覆盖我们的全局变量
            Object.defineProperty(window, '__webAutomationProtected', {
                value: true,
                writable: false,
                configurable: false
            });
            
            // 立即显示初始化遮罩（仅首次，且仅顶层窗口）
            console.log('[WebAutomation] 页面开始加载，检查是否需要显示初始化遮罩');
            (function() {
                try {
                    // 仅在顶层窗口显示遮罩
                    if (window.top !== window.self) { return; }
                } catch (e) { /* ignore */ }
                
                // 已完成首次全量初始化后，不再显示遮罩
                try {
                    if (sessionStorage.getItem('__automation_init_done') === '1') {
                        return;
                    }
                } catch (e) { /* ignore */ }

                var showOverlayImmediately = function() {
                    if (typeof window.__automationShowOverlay === 'function') {
                        if (window.location.href === 'about:blank') {
                            window.__automationShowOverlay('准备导航到目标页面...');
                        } else {
                            window.__automationShowOverlay('页面加载中，正在初始化事件监听器...');
                        }
                        console.log('[WebAutomation] 遮罩已显示，当前页面:', window.location.href);
                    }
                };
                
                // 立即尝试显示
                showOverlayImmediately();
                // 保险：短延时重试，覆盖早期阶段
                setTimeout(showOverlayImmediately, 50);
                setTimeout(showOverlayImmediately, 200);
                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', showOverlayImmediately);
                }
            })();
            
            // 初始化遮罩函数，提示用户等待初始化完成（仅注入函数，不自动显示）
            try {
                if (!window.__automationOverlayInitialized) {
                    window.__automationOverlayInitialized = true;
                window.__automationShowOverlay = function(message) {
                    try {
                        var existing = document.getElementById('webautomation-init-overlay');
                        if (existing) {
                            var m = document.getElementById('webautomation-init-message');
                            if (m) m.textContent = message || '正在初始化，请稍候...';
                        } else {
                            var ov = document.createElement('div');
                            ov.id = 'webautomation-init-overlay';
                            ov.style.cssText = 'position:fixed !important;top:0 !important;left:0 !important;width:100% !important;height:100% !important;background:rgba(0,0,0,0.55) !important;backdrop-filter:blur(1px) !important;z-index:2147483647 !important;display:flex !important;align-items:center !important;justify-content:center !important;pointer-events:all !important;';
                            var box = document.createElement('div');
                            box.style.cssText = 'background:#111 !important;color:#fff !important;padding:16px 22px !important;border-radius:10px !important;border:2px solid #3aa3ff !important;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica Neue,Arial,sans-serif !important;box-shadow:0 6px 30px rgba(0,0,0,0.35) !important;text-align:center !important;';
                            var spinner = document.createElement('div');
                            spinner.style.cssText = 'margin:0 auto 10px !important;width:24px !important;height:24px !important;border-radius:50% !important;border:3px solid #3aa3ff !important;border-top-color:transparent !important;animation:webautomation-spin 0.8s linear infinite !important;';
                            var msg = document.createElement('div');
                            msg.id = 'webautomation-init-message';
                            msg.style.cssText = 'font-size:14px !important;letter-spacing:0.2px !important;color:#fff !important;';
                            msg.textContent = message || '正在初始化事件监听器，请稍候...';
                            box.appendChild(spinner);
                            box.appendChild(msg);
                            ov.appendChild(box);
                            
                            // 智能添加到DOM - 如果body存在就添加到body，否则添加到html
                            var targetElement = document.body || document.documentElement;
                            if (targetElement) {
                                targetElement.appendChild(ov);
                            } else {
                                // 如果连html都没有，等待DOM准备
                                var addOverlay = function() {
                                    var target = document.body || document.documentElement;
                                    if (target) {
                                        target.appendChild(ov);
                                    }
                                };
                                if (document.readyState === 'loading') {
                                    document.addEventListener('DOMContentLoaded', addOverlay);
                                } else {
                                    setTimeout(addOverlay, 10);
                                }
                            }
                            var style = document.getElementById('webautomation-init-style');
                            if (!style) {
                                style = document.createElement('style');
                                style.id = 'webautomation-init-style';
                                style.textContent = '@keyframes webautomation-spin { from { transform: rotate(0deg);} to { transform: rotate(360deg);} }';
                                document.head.appendChild(style);
                            }
                        }
                    } catch (e) {}
                };
                window.__automationUpdateOverlay = function(message) {
                    try { var m = document.getElementById('webautomation-init-message'); if (m) m.textContent = message || '正在初始化事件监听器，请稍候...'; } catch (e) {}
                };
                window.__automationHideOverlay = function() {
                    try {
                        var ov = document.getElementById('webautomation-init-overlay');
                        if (ov) ov.remove();
                        var style = document.getElementById('webautomation-init-style');
                        if (style) style.remove();
                        // 标记首次全量初始化完成，后续不再显示初始化遮罩
                        try { sessionStorage.setItem('__automation_init_done', '1'); } catch (e) {}
                    } catch (e) {}
                };
            }
        } catch (e) {}
        
        // 确保只初始化一次，并增强持久性
        if (!window.webAutomationEvents) {
            // 使用defineProperty增强持久性，防止被页面脚本覆盖
            Object.defineProperty(window, 'webAutomationEvents', {
                value: [],
                writable: true,
                configurable: false  // 防止被delete
            });
            console.log('[WebAutomation] 事件数组已创建（受保护）');
            
            // 工具：过滤注入/高亮类，避免选择器包含临时样式（增强持久性）
            Object.defineProperty(window, '__isInstrumentationClass', {
                value: function(cls) {
                if (!cls) return false;
                if (cls === 'element-hover-highlight') return true;
                if (cls === 'element-selection-hover-rect') return true;
                if (cls.indexOf('webautomation-') === 0) return true;
                if (cls.indexOf('element-selection-') === 0) return true;
                return false;
                },
                writable: false,
                configurable: false
            });
            Object.defineProperty(window, '__filterInstrumentationClasses', {
                value: function(className) {
                if (!className || typeof className !== 'string') return [];
                return className.split(' ').filter(c => c && !window.__isInstrumentationClass(c));
                },
                writable: false,
                configurable: false
            });
            
            // 生成CSS选择器函数（过滤临时类名，增强持久性）
            Object.defineProperty(window, 'generateSelector', {
                value: function(element) {
                try {
                    if (!element) return 'unknown';
                    
                    if (element.id) {
                        return '#' + element.id;
                    }
                    
                    if (element.className && typeof element.className === 'string') {
                        const classes = window.__filterInstrumentationClasses(element.className);
                        if (classes.length > 0) {
                            return '.' + classes.join('.');
                        }
                    }
                    
                    let selector = element.tagName.toLowerCase();
                    
                    if (element.type) {
                        selector += `[type="${element.type}"]`;
                    }
                    
                    if (element.name) {
                        selector += `[name="${element.name}"]`;
                    }
                    
                    // 如果还是不够特异，添加nth-child
                    const parent = element.parentElement;
                    if (parent) {
                        const siblings = Array.from(parent.children).filter(
                            child => child.tagName === element.tagName
                        );
                        if (siblings.length > 1) {
                            const index = siblings.indexOf(element) + 1;
                            selector += `:nth-child(${index})`;
                        }
                    }
                    
                    return selector;
                } catch (e) {
                    console.error('[WebAutomation] 选择器生成失败:', e);
                    return 'unknown';
                }
                },
                writable: false,
                configurable: false
            });
            
            // 生成更健壮的CSS路径（包含层级与nth-of-type，过滤临时类名，增强持久性）
            Object.defineProperty(window, 'generateRobustSelector', {
                value: function(element) {
                try {
                    if (!element) return 'unknown';
                    if (element.id) return '#' + element.id;
                    const parts = [];
                    let el = element;
                    while (el && el.nodeType === 1 && parts.length < 6) { // 限制深度避免超长
                        let part = el.tagName.toLowerCase();
                        if (el.id) { part = part + '#' + el.id; parts.unshift(part); break; }
                        const className = (el.className || '').trim();
                        if (className && typeof className === 'string') {
                            const filtered = window.__filterInstrumentationClasses(className);
                            const firstClass = filtered[0];
                            if (firstClass) part += '.' + firstClass;
                        }
                        let nth = 1, sib = el;
                        while ((sib = sib.previousElementSibling)) {
                            if (sib.tagName === el.tagName) nth++;
                        }
                        part += `:nth-of-type(${nth})`;
                        parts.unshift(part);
                        el = el.parentElement;
                    }
                    return parts.join(' > ');
                } catch (e) { return window.generateSelector(element); }
                },
                writable: false,
                configurable: false
            });
            
            // 等待DOM就绪的函数
            function setupEventListeners() {
                // 点击事件监听（冒泡阶段），在元素选择模式下跳过
                document.addEventListener('click', (event) => {
                    try {
                        if (window.elementSelectionMode) {
                            // 选择模式下，普通点击不应被录制
                            return;
                        }
                    } catch (e) { /* ignore */ }
                    try {
                        const element = event.target;
                        const selector = window.generateSelector(element);
                        const robust = window.generateRobustSelector(element);
                        
                        const eventData = {
                            type: 'click',
                            selector: selector,
                            robust_selector: robust,
                            text_content: element.textContent?.trim() || '',
                            timestamp: Date.now(),
                            x: event.clientX,
                            y: event.clientY
                        };
                        
                        // 预抓取元素快照，避免导航后选择器指向其它元素
                        try {
                            const rect = element.getBoundingClientRect();
                            const attrs = {};
                            for (const a of Array.from(element.attributes || [])) { attrs[a.name] = a.value; }
                            const parent = element.parentElement;
                            const parentSummary = parent ? {
                                tagName: parent.tagName,
                                id: parent.id,
                                className: parent.className,
                                children: Array.from(parent.children).slice(0, 10).map(c => ({
                                    tagName: c.tagName,
                                    id: c.id,
                                    className: c.className,
                                    textContent: (c.textContent || '').trim().substring(0, 80)
                                }))
                            } : null;
                            eventData.element_snapshot = {
                                selector: selector,
                                robust_selector: robust,
                                element: {
                                    tagName: element.tagName,
                                    id: element.id,
                                    className: element.className,
                                    textContent: (element.textContent || '').trim(),
                                    innerHTML: element.innerHTML,
                                    outerHTML: element.outerHTML,
                                    attributes: attrs,
                                    boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left },
                                    isVisible: element.offsetParent !== null,
                                    computedStyle: ''
                                },
                                parent: parentSummary,
                                page_title: document.title,
                                page_url: location.href,
                                timestamp: Date.now()
                            };
                        } catch (snapshotErr) { /* ignore */ }
                        
                        // 先通过桥接通道上报，再入队；标记避免重复处理
                        try { if (typeof window.__automationEmit === 'function') { eventData.__delivered = true; window.__automationEmit(eventData); } } catch (e) {}
                        window.webAutomationEvents.push(eventData);
                        console.log('[WebAutomation] Context-点击事件已捕获:', eventData);
                    } catch (e) {
                        console.error('[WebAutomation] 点击事件处理失败:', e);
                    }
                }, true);
                
                // 输入事件监听
                document.addEventListener('input', (event) => {
                    try {
                        const element = event.target;
                        const selector = window.generateSelector(element);
                        
                        const eventData = {
                            type: 'input',
                            selector: selector,
                            value: element.value || '',
                            timestamp: Date.now()
                        };
                        
                        try { if (typeof window.__automationEmit === 'function') { eventData.__delivered = true; window.__automationEmit(eventData); } } catch (e) {}
                        window.webAutomationEvents.push(eventData);
                        console.log('[WebAutomation] Context-输入事件已捕获:', eventData);
                    } catch (e) {
                        console.error('[WebAutomation] 输入事件处理失败:', e);
                    }
                }, true);
                
                // 在页面卸载前尽力上报一次导航拦截事件
                const navHandler = () => {
                    try {
                        const navEvent = {
                            type: 'navigation_intercepted',
                            url: location.href,
                            timestamp: Date.now()
                        };
                        try { if (typeof window.__automationEmit === 'function') { navEvent.__delivered = true; window.__automationEmit(navEvent); } } catch (e) {}
                        window.webAutomationEvents.push(navEvent);
                    } catch (e) {}
                };
                window.addEventListener('beforeunload', navHandler, { capture: true });
                window.addEventListener('pagehide', navHandler, { capture: true });
                
                console.log('[WebAutomation] Context事件监听器设置完成');
            }
            
            // 立即尝试设置事件监听器，如果DOM未就绪则等待
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', setupEventListeners);
            } else {
                setupEventListeners();
            }
            
            // 添加元素选择功能（仅在未定义时初始化，避免后续导航覆盖）
            if (typeof window.elementSelectionMode === 'undefined') window.elementSelectionMode = false;
            if (typeof window.hoveredElement === 'undefined') window.hoveredElement = null;
            if (typeof window.elementSelectionCallback === 'undefined') window.elementSelectionCallback = null;
            
            // 元素选择相关样式
            window.addSelectionStyles = function() {
                if (document.getElementById('element-selection-styles')) return;
                
                const styles = document.createElement('style');
                styles.id = 'element-selection-styles';
                styles.textContent = `
                    .element-hover-highlight {
                        outline: 3px solid #007bff !important;
                        outline-offset: 2px !important;
                        background-color: rgba(0, 123, 255, 0.12) !important;
                        cursor: pointer !important;
                        position: relative !important;
                        z-index: 2147483646 !important;
                        box-shadow: 0 0 0 3px rgba(0,123,255,0.35), 0 0 16px rgba(0,123,255,0.55) !important;
                        transition: box-shadow 60ms ease, background-color 60ms ease !important;
                    }
                    #element-selection-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0, 0, 0, 0.3);
                        z-index: 99998;
                        pointer-events: none;
                        transition: clip-path 60ms linear;
                    }
                    #element-selection-notice {
                        position: fixed;
                        top: 20px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: #007bff;
                        color: white;
                        padding: 15px 25px;
                        border-radius: 8px;
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                        font-size: 16px;
                        z-index: 99999;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                    }
                    #element-selection-hover-rect {
                        position: fixed;
                        border: 3px solid #00b7ff;
                        box-shadow: 0 0 0 3px rgba(0,183,255,0.35), 0 0 16px rgba(0,183,255,0.55);
                        border-radius: 4px;
                        z-index: 2147483647;
                        pointer-events: none;
                        display: none;
                    }
                `;
                document.head.appendChild(styles);
            };
            
            // 启用元素选择模式
            window.enableElementSelection = function() {
                if (window.elementSelectionMode) return;
                
                console.log('[WebAutomation] 启用元素选择模式');
                window.elementSelectionMode = true;
                window.addSelectionStyles();
                
                // 创建遮罩层和提示
                const overlay = document.createElement('div');
                overlay.id = 'element-selection-overlay';
                document.body.appendChild(overlay);
                
                const notice = document.createElement('div');
                notice.id = 'element-selection-notice';
                notice.innerHTML = '🎯 选择包含目标内容的元素<br><small>点击确认选择，按ESC取消</small>';
                document.body.appendChild(notice);
                
                // 悬浮矩形框（高亮边框，不依赖目标元素样式）
                const hoverRect = document.createElement('div');
                hoverRect.id = 'element-selection-hover-rect';
                document.body.appendChild(hoverRect);
                
                // 鼠标移动事件
                document.addEventListener('mousemove', window.handleElementHover, true);
                document.addEventListener('click', window.handleElementClick, true);
                document.addEventListener('keydown', window.handleElementSelectionKeydown, true);
            };
            
            // 禁用元素选择模式
            window.disableElementSelection = function() {
                if (!window.elementSelectionMode) return;
                
                console.log('[WebAutomation] 禁用元素选择模式');
                window.elementSelectionMode = false;
                
                // 清理高亮
                if (window.hoveredElement) {
                    window.hoveredElement.classList.remove('element-hover-highlight');
                    window.hoveredElement = null;
                }
                
                // 移除事件监听
                document.removeEventListener('mousemove', window.handleElementHover, true);
                document.removeEventListener('click', window.handleElementClick, true);
                document.removeEventListener('keydown', window.handleElementSelectionKeydown, true);
                
                // 清理UI元素
                const overlay = document.getElementById('element-selection-overlay');
                if (overlay) overlay.remove();
                
                const notice = document.getElementById('element-selection-notice');
                if (notice) notice.remove();
                
                const hoverRect = document.getElementById('element-selection-hover-rect');
                if (hoverRect) hoverRect.remove();
                
                const styles = document.getElementById('element-selection-styles');
                if (styles) styles.remove();
            };
            
            // 选择可见且有盒模型的祖先，避免选到很小/不可见节点
            window.findHighlightTarget = function(node) {
                try {
                    const minWidth = 40;
                    const minHeight = 20;
                    const isVisible = (el) => {
                        if (!el || el === document.body || el === document.documentElement) return false;
                        const cs = window.getComputedStyle(el);
                        if (cs.display === 'contents') return false;
                        if (cs.visibility === 'hidden' || cs.opacity === '0') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width >= 2 && rect.height >= 2;
                    };
                    let el = node;
                    let candidate = node;
                    while (el && el !== document.body) {
                        if (isVisible(el)) {
                            candidate = el;
                            const r = el.getBoundingClientRect();
                            if (r.width >= minWidth && r.height >= minHeight) break;
                        }
                        el = el.parentElement;
                    }
                    return candidate;
                } catch (e) { return node; }
            };
            
            // 处理鼠标悬停
            window.handleElementHover = function(event) {
                if (!window.elementSelectionMode) return;
                
                const raw = event.target;
                const element = window.findHighlightTarget(raw);
                if (element === window.hoveredElement) return;
                
                // 清除之前的高亮
                if (window.hoveredElement) {
                    window.hoveredElement.classList.remove('element-hover-highlight');
                }
                
                // 高亮当前元素
                if (element && element !== document.body && element !== document.documentElement) {
                    element.classList.add('element-hover-highlight');
                    window.hoveredElement = element;
                    // 更新悬浮矩形与遮罩挖洞
                    try {
                        const r = element.getBoundingClientRect();
                        const pad = 4;
                        const left = Math.max(0, Math.floor(r.left - pad));
                        const top = Math.max(0, Math.floor(r.top - pad));
                        const right = Math.min(window.innerWidth, Math.ceil(r.right + pad));
                        const bottom = Math.min(window.innerHeight, Math.ceil(r.bottom + pad));
                        const w = Math.max(0, right - left);
                        const h = Math.max(0, bottom - top);
                        const hoverRect = document.getElementById('element-selection-hover-rect');
                        if (hoverRect) {
                            hoverRect.style.display = 'block';
                            hoverRect.style.left = left + 'px';
                            hoverRect.style.top = top + 'px';
                            hoverRect.style.width = w + 'px';
                            hoverRect.style.height = h + 'px';
                        }
                        const overlay = document.getElementById('element-selection-overlay');
                        if (overlay) {
                            overlay.style.clipPath = `path('evenodd, M 0 0 H ${window.innerWidth} V ${window.innerHeight} H 0 Z M ${left} ${top} H ${right} V ${bottom} H ${left} Z')`;
                        }
                    } catch (e) { /* ignore */ }
                }
            };
            
            // 处理点击选择
            window.handleElementClick = function(event) {
                if (!window.elementSelectionMode) return;
                
                event.preventDefault();
                event.stopPropagation();
                
                const raw = event.target;
                const element = window.findHighlightTarget(raw);
                if (element && element !== document.body && element !== document.documentElement) {
                    // 在生成选择器前移除临时高亮类，避免被拼入class
                    try { element.classList.remove('element-hover-highlight'); } catch (_) {}
                    // 记录选中的元素信息
                    const selector = window.generateSelector(element);
                    const robust = window.generateRobustSelector(element);
                    const elementInfo = {
                        type: 'element_selected',
                        selector: selector,
                        robust_selector: robust,
                        tagName: element.tagName.toLowerCase(),
                        id: element.id || null,
                        className: element.className || null,
                        textContent: element.textContent?.trim().substring(0, 200) || '',
                        timestamp: Date.now()
                    };
                    
                    // 将选择信息添加到事件队列
                    window.webAutomationEvents.push(elementInfo);
                    
                    console.log('[WebAutomation] 元素已选择:', elementInfo);
                    window.disableElementSelection();
                }
            };
            
            // 处理键盘事件
            window.handleElementSelectionKeydown = function(event) {
                if (!window.elementSelectionMode) return;
                
                if (event.key === 'Escape') {
                    event.preventDefault();
                    console.log('[WebAutomation] 用户取消元素选择');
                    window.disableElementSelection();
                }
            };
            
            // 全局快捷键监听 (Cmd+Y / Ctrl+Y) - 同时监听document与window，大小写兼容
            function __handleSelectionHotkey(event) {
                try {
                    const key = (event.key || '').toLowerCase();
                    if ((event.metaKey || event.ctrlKey) && key === 'y') {
                        event.preventDefault();
                        console.log('[WebAutomation] 快捷键触发元素选择');
                        // 通知Python端进入元素选择模式
                        window.webAutomationEvents.push({
                            type: 'element_selection_mode_start',
                            timestamp: Date.now()
                        });
                        window.enableElementSelection();
                    }
                } catch (_) {}
            }
            document.addEventListener('keydown', __handleSelectionHotkey, true);
            try { window.addEventListener('keydown', __handleSelectionHotkey, true); } catch (e) {}
            
            // 兼容旧浏览器/不同布局下的快捷键（key可能是'Y'）
            document.addEventListener('keydown', function(event){
                try {
                    if ((event.metaKey || event.ctrlKey) && event.key === 'Y') {
                        __handleSelectionHotkey(event);
                    }
                } catch (_) {}
            }, true);
            try { window.addEventListener('keydown', function(event){
                try {
                    if ((event.metaKey || event.ctrlKey) && event.key === 'Y') {
                        __handleSelectionHotkey(event);
                    }
                } catch (_) {}
            }, true); } catch (e) {}
            
            
            console.log('[WebAutomation] Context初始化完成，DOM状态:', document.readyState);
        } else {
            console.log('[WebAutomation] Context事件监听器已存在，跳过初始化');
        }
        """)
            console.print("✅ Context级别JavaScript已注入")
            
            self.page = await self.context.new_page()
            
            # 先导航到空白页面，触发Context级别的JavaScript注入和自动遮罩显示
            console.print("🔄 初始化页面并自动显示遮罩...")
            await self.page.goto("about:blank")
            console.print("⏳ JavaScript自动遮罩已激活")
            
            # 短暂等待确保JavaScript初始化完成
            await asyncio.sleep(0.5)
            
            # 现在导航到目标页面，遮罩会自动更新并持续显示
            console.print(f"🌐 导航到: {url}")
            await self.page.goto(url)
            console.print("📄 页面导航完成，遮罩应持续显示直到事件监听器就绪")
            
            # 等待页面加载完成后再设置事件监听器
            await asyncio.sleep(1)
            
            # 缓存页面标题，避免后续访问时页面已关闭
            try:
                self.cached_page_title = await self.page.title()
            except Exception as e:
                console.print(f"⚠️  无法获取页面标题: {e}", style="yellow")
                self.cached_page_title = 'Unknown'
            
            try:
                # 注入事件监听器，但不立即移除遮罩
                await self._setup_event_listeners()
                console.print("✅ 事件监听器设置完成，等待JavaScript完全就绪...")
                # 更新遮罩文案：正在验证JavaScript状态
                try:
                    await self.page.evaluate("window.__automationUpdateOverlay && window.__automationUpdateOverlay('正在验证事件监听器是否就绪...')")
                except Exception:
                    pass
            except Exception as e:
                console.print(f"⚠️  事件监听器设置失败: {e}", style="yellow")
                console.print(f"⚠️  错误类型: {type(e).__name__}", style="yellow")
                console.print(f"⚠️  错误详情: {str(e)[:200]}", style="yellow")
                console.print("📝 录制将继续，但可能无法捕获所有事件", style="yellow")
                # 监听器设置失败时，移除初始化遮罩，避免页面被永久遮挡
                try:
                    await self.page.evaluate("window.__automationHideOverlay && window.__automationHideOverlay()")
                    console.print("✅ 初始化遮罩已移除（监听器设置失败）")
                except Exception as e2:
                    console.print(f"⚠️ 无法移除遮罩: {e2}", style="yellow")
            
            # 启动HTML监控任务
            try:
                self.html_monitor_task = asyncio.create_task(self._monitor_html_changes())
                console.print("✅ HTML监控已启动")
            except Exception as e:
                console.print(f"⚠️  HTML监控启动失败: {e}", style="yellow")
            
            # 设置元素选择功能，但遮罩将在event_listener确认JavaScript就绪后移除
            console.print("🎯 元素选择功能已就绪")
            console.print("💡 按 [bold blue]Cmd+Y[/bold blue] (Mac) 或 [bold blue]Ctrl+Y[/bold blue] (Windows) 选择返回内容区域")
            console.print("⏳ 正在最终验证事件监听器状态，请稍候...")
            
            # 等待用户操作  
            console.print("📝 请在浏览器中执行您的操作...")
            console.print("🛑 [bold yellow]结束录制的方法：[/bold yellow]")
            console.print("   1️⃣  按 [bold red]Ctrl+C[/bold red]")
            console.print("   2️⃣  关闭浏览器窗口")
            console.print("   3️⃣  在浏览器地址栏输入: [blue]about:blank[/blue]")
            
            recording_active = True
            while recording_active:
                try:
                    # 检查程序化停止标志（最优先检查）
                    if self.stop_recording_flag:
                        console.print("\n🛑 检测到程序化停止信号，自动结束录制")
                        recording_active = False
                        break
                    
                    # 检查是否用户选择了元素（优先检查）
                    if self.recording_interrupted:
                        console.print("\n🎯 检测到用户完成元素选择，自动结束录制")
                        recording_active = False
                        break
                    
                    # 检查页面是否还存在或导航到结束页面
                    try:
                        # 首先检查页面对象是否还有效
                        if not self.page or not self.context:
                            console.print("\n🔍 检测到页面或上下文对象已失效，自动结束录制")
                            recording_active = False
                            break
                        
                        current_url = self.page.url
                        if current_url == "about:blank":
                            console.print("\n🔍 检测到导航到about:blank，自动结束录制")
                            recording_active = False
                            break
                            
                        # 检查页面是否还活着 - 使用更稳定的检查方式
                        try:
                            # 尝试获取页面状态，但不因为导航失败而结束录制
                            page_state = await self.page.evaluate("document.readyState")
                            # console.print(f"🔍 页面状态检查通过: {page_state}")
                        except Exception as title_error:
                            # 如果是导航相关的错误，不结束录制
                            error_msg = str(title_error).lower()
                            if any(keyword in error_msg for keyword in ['navigation', 'destroyed', 'detached']):
                                console.print(f"🌐 页面正在导航中，继续监控: {error_msg}")
                                await asyncio.sleep(1)  # 等待导航完成
                                continue  # 继续下一次循环
                            else:
                                # 如果是其他类型的错误，才认为页面关闭
                                raise title_error
                        
                        # 检查浏览器上下文是否还存在
                        if len(self.context.pages) == 0:
                            console.print("\n🔍 检测到所有页面已关闭，自动结束录制")
                            recording_active = False
                            break
                            
                    except Exception as page_error:
                        # 更精确地判断异常类型
                        error_msg = str(page_error).lower()
                        if any(keyword in error_msg for keyword in ['navigation', 'destroyed', 'detached', 'changing']):
                            console.print(f"🌐 页面导航中出现异常，继续监控: {error_msg}")
                            await asyncio.sleep(1)  # 等待导航稳定
                            continue
                        else:
                            console.print(f"\n🔍 检测到页面真正关闭，自动结束录制: {page_error}")
                            recording_active = False
                            break
                    
                    # 短暂等待，让Ctrl+C有机会被捕获
                    await asyncio.sleep(0.1)
                    
                except KeyboardInterrupt:
                    console.print("\n🛑 用户按下Ctrl+C，录制已停止")
                    self.recording_interrupted = True
                    recording_active = False
                    break
                except Exception as e:
                    console.print(f"\n⚠️  录制过程中出现错误: {e}", style="yellow")
                    console.print("🛑 录制已停止")
                    recording_active = False
                    break
            
            # 尝试保存认证状态
            try:
                if self.context:
                    auth_state_path = session_dir / 'auth_state.json'
                    await self.context.storage_state(path=str(auth_state_path))
                    console.print("✅ 认证状态已保存")
                else:
                    console.print("⚠️  上下文已关闭，跳过认证状态保存", style="yellow")
            except Exception as e:
                console.print(f"⚠️  保存认证状态失败: {e}", style="yellow")
            
            # 刷新所有待处理的输入操作
            if self.pending_input_operations:
                await self._flush_all_pending_inputs()
            
            # 停止HTML监控
            if self.html_monitor_task:
                self.html_monitor_task.cancel()
                try:
                    await self.html_monitor_task
                except asyncio.CancelledError:
                    pass
                console.print("✅ HTML监控已停止")
            
            
            # 保存HTML缓存
            try:
                await self._save_html_cache(session_dir)
            except Exception as e:
                console.print(f"⚠️  保存HTML缓存失败: {e}", style="yellow")
            
            # 保存会话数据
            try:
                await self._save_session_data(session_dir, name, url)
                if self.recording_interrupted:
                    console.print("✅ 会话数据已保存（录制已中断）")
                else:
                    console.print("✅ 会话数据已保存")
            except Exception as e:
                console.print(f"⚠️  保存会话数据时出错: {e}", style="yellow")
                if self.recording_interrupted:
                    console.print("ℹ️  录制被中断，使用缓存数据保存会话", style="blue")
                else:
                    console.print("ℹ️  会话录制已完成，但部分数据可能未保存", style="blue")
            
            # 尝试关闭浏览器
            try:
                await self.browser.close()
            except Exception:
                # 浏览器可能已经关闭，忽略错误
                pass
        
        return self.session_id
    
    def stop_recording(self):
        """程序化停止录制（供外部调用）"""
        console.print("🛑 收到停止录制信号...")
        self.stop_recording_flag = True
        console.print("✅ 录制停止标志已设置")
    
    async def remove_initialization_overlay(self):
        """移除初始化遮罩（供事件监听器调用）"""
        try:
            if self.page:
                await self.page.evaluate("window.__automationHideOverlay && window.__automationHideOverlay()")
                console.print("✅ 初始化遮罩已移除 - 事件监听器完全就绪")
                console.print("🎉 [bold green]现在可以开始操作网页了！[/bold green]")
        except Exception as e:
            console.print(f"⚠️ 无法移除遮罩: {e}", style="yellow")
    
    async def initialize_recording(
        self, 
        name: str, 
        url: str, 
        output_dir: str = 'sessions', 
        custom_session_path: Optional[str] = None,
        auth_state_file: Optional[str] = None,
        headless: bool = False,
        viewport: Optional[Dict[str, int]] = None
    ) -> str:
        """初始化录制会话（非阻塞）"""
        
        # 处理session路径
        if custom_session_path:
            session_dir = Path(custom_session_path)
            self.session_id = session_dir.name
            console.print(f"📁 使用自定义路径: {session_dir}")
            
            # 如果路径已存在，先删除再创建（覆盖模式）
            if session_dir.exists():
                console.print(f"⚠️  路径已存在，将覆盖: {session_dir}")
                import shutil
                shutil.rmtree(session_dir)
                console.print("🗑️  已删除旧文件")
        else:
            self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            session_dir = Path(output_dir) / self.session_id
        
        # 创建会话目录
        session_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"📁 会话目录已创建: {session_dir}")
        
        # 保存会话目录路径供后续使用
        self.session_dir = session_dir
        
        # 创建截图目录
        screenshots_dir = session_dir / 'screenshots'
        screenshots_dir.mkdir(exist_ok=True)
        
        console.print(f"📁 会话目录: {session_dir}")
        console.print("🎬 初始化浏览器录制...")
        
        # 验证URL格式
        url = self._validate_url(url)
        
        # 启动浏览器但不进入阻塞循环
        playwright = await async_playwright().start()
        
        # 启动浏览器
        self.browser = await playwright.chromium.launch(
            headless=headless,
            slow_mo=1000,  # 减慢操作以便观察
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        # 创建上下文（使用认证状态如果提供了）
        default_viewport = viewport or {'width': 1920, 'height': 1080}
        context_kwargs = {
            'viewport': default_viewport,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        if auth_state_file and Path(auth_state_file).exists():
            context_kwargs['storage_state'] = auth_state_file
            console.print(f"🔐 使用认证状态: {auth_state_file}", style="blue")
        
        self.context = await self.browser.new_context(**context_kwargs)
        
        # 在context级别注入JavaScript事件监听器
        await self._inject_context_javascript()
        
        self.page = await self.context.new_page()
        
        # 先导航到空白页面，触发Context级别的JavaScript注入和自动遮罩显示
        console.print("🔄 初始化页面并自动显示遮罩...")
        await self.page.goto("about:blank")
        console.print("⏳ JavaScript自动遮罩已激活")
        
        # 短暂等待确保JavaScript初始化完成
        await asyncio.sleep(0.5)
        
        # 现在导航到目标页面，遮罩会自动更新并持续显示
        console.print(f"🌐 导航到: {url}")
        await self.page.goto(url)
        console.print("📄 页面导航完成，遮罩应持续显示直到事件监听器就绪")
        
        # 等待页面加载完成后再设置事件监听器
        await asyncio.sleep(1)
        
        # 缓存页面标题，避免后续访问时页面已关闭
        try:
            self.cached_page_title = await self.page.title()
        except Exception as e:
            console.print(f"⚠️  无法获取页面标题: {e}", style="yellow")
            self.cached_page_title = 'Unknown'
        
        try:
            # 注入事件监听器
            await self._setup_event_listeners()
            console.print("✅ 事件监听器设置完成")
        except Exception as e:
            console.print(f"⚠️  事件监听器设置失败: {e}", style="yellow")
            console.print("📝 录制将继续，但可能无法捕获所有事件", style="yellow")
        
        # 启动HTML监控任务
        try:
            self.html_monitor_task = asyncio.create_task(self._monitor_html_changes())
            console.print("✅ HTML监控已启动")
        except Exception as e:
            console.print(f"⚠️  HTML监控启动失败: {e}", style="yellow")
        
        console.print("✅ 录制初始化完成，准备接收程序化操作")
        
        return self.session_id
    
    async def record_programmatic_action(
        self, 
        action: str, 
        selector: str, 
        value: str = "", 
        text_content: str = ""
    ):
        """手动记录程序化操作（供外部调用）"""
        if not self.session_id:
            console.print("⚠️ 录制会话未初始化，跳过操作记录")
            return
            
        try:
            # 构造事件数据
            event_data = {
                'selector': selector,
                'value': value,
                'text_content': text_content,
                'timestamp': datetime.now().timestamp() * 1000  # JavaScript时间戳格式
            }
            
            # 生成步骤ID
            step_id = len(self.operations) + 1
            
            console.print(f"📝 记录程序化操作: {action} - {selector}")
            
            # 记录操作
            await self._record_operation(action, event_data, step_id)
            
            console.print(f"✅ 程序化操作记录完成: {action}")
            
        except Exception as e:
            console.print(f"❌ 记录程序化操作失败: {e}")
            import traceback
            console.print(f"错误详情: {traceback.format_exc()}")
    
    def get_recorder_page(self):
        """获取录制器的页面实例（供外部使用）"""
        return self.page
    
    async def _inject_context_javascript(self):
        """注入Context级别的JavaScript代码"""
        await self.context.add_init_script("""
        console.log('[WebAutomation] Context级别初始化事件监听器');
        
        // 确保只初始化一次，并增强持久性
        if (!window.webAutomationEvents) {
            // 使用defineProperty增强持久性，防止被页面脚本覆盖
            Object.defineProperty(window, 'webAutomationEvents', {
                value: [],
                writable: true,
                configurable: false  // 防止被delete
            });
            console.log('[WebAutomation] 事件数组已创建（受保护）');
            
            // 生成CSS选择器函数
            window.generateSelector = function(element) {
                try {
                    if (!element) return 'unknown';
                    
                    if (element.id) {
                        return '#' + element.id;
                    }
                    
                    if (element.className && typeof element.className === 'string') {
                        const classes = element.className.split(' ').filter(c => c.trim());
                        if (classes.length > 0) {
                            return '.' + classes.join('.');
                        }
                    }
                    
                    let selector = element.tagName.toLowerCase();
                    
                    if (element.type) {
                        selector += `[type="${element.type}"]`;
                    }
                    
                    if (element.name) {
                        selector += `[name="${element.name}"]`;
                    }
                    
                    // 如果还是不够特异，添加nth-child
                    const parent = element.parentElement;
                    if (parent) {
                        const siblings = Array.from(parent.children).filter(
                            child => child.tagName === element.tagName
                        );
                        if (siblings.length > 1) {
                            const index = siblings.indexOf(element) + 1;
                            selector += `:nth-child(${index})`;
                        }
                    }
                    
                    return selector;
                } catch (e) {
                    console.error('[WebAutomation] 选择器生成失败:', e);
                    return 'unknown';
                }
            };
        } else {
            console.log('[WebAutomation] Context事件监听器已存在，跳过初始化');
        }
        """)
        console.print("✅ Context级别JavaScript已注入")
        
    async def finalize_and_save(self, session_dir: Path, name: str, url: str):
        """完成录制并保存数据"""
        # 停止HTML监控
        if self.html_monitor_task:
            self.html_monitor_task.cancel()
            try:
                await self.html_monitor_task
            except asyncio.CancelledError:
                pass
            console.print("✅ HTML监控已停止")
        
        # 刷新所有待处理的输入操作
        if self.pending_input_operations:
            await self._flush_all_pending_inputs()
        
        # 尝试保存认证状态
        try:
            if self.context:
                auth_state_path = session_dir / 'auth_state.json'
                await self.context.storage_state(path=str(auth_state_path))
                console.print("✅ 认证状态已保存")
        except Exception as e:
            console.print(f"⚠️  保存认证状态失败: {e}", style="yellow")
        
        # 保存HTML缓存
        try:
            await self._save_html_cache(session_dir)
        except Exception as e:
            console.print(f"⚠️  保存HTML缓存失败: {e}", style="yellow")
        
        # 保存会话数据
        try:
            await self._save_session_data(session_dir, name, url)
            console.print("✅ 会话数据已保存")
        except Exception as e:
            console.print(f"⚠️  保存会话数据时出错: {e}", style="yellow")
        
        # 尝试关闭浏览器
        try:
            await self.browser.close()
        except Exception:
            # 浏览器可能已经关闭，忽略错误
            pass
    
    async def _setup_event_listeners(self):
        """设置事件监听器"""
        step_counter = {'count': 0}
        
        async def safe_handle_click(event_data):
            try:
                # 检查是否是元素选择模式中的点击，如果是则跳过记录
                if self.element_selection_mode:
                    console.print(f"🎯 元素选择模式中的点击，跳过记录: {event_data.get('selector', 'N/A')}")
                    return
                
                step_counter['count'] += 1
                console.print(f"🖱️  收到点击事件 - 步骤 {step_counter['count']}: {event_data}")
                await self._record_operation('click', event_data, step_counter['count'])
                console.print(f"✅ 点击事件处理完成 - 步骤 {step_counter['count']}")
            except Exception as e:
                console.print(f"❌ 处理点击事件失败: {e}")
                console.print(f"❌ 事件数据: {event_data}")
                import traceback
                console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
        
        async def safe_handle_input(event_data):
            try:
                step_counter['count'] += 1
                console.print(f"⌨️  收到输入事件 - 步骤 {step_counter['count']}: {event_data}")
                await self._handle_merged_input('input', event_data, step_counter['count'])
                console.print(f"✅ 输入事件处理完成 - 步骤 {step_counter['count']}")
            except Exception as e:
                console.print(f"❌ 处理输入事件失败: {e}")
                console.print(f"❌ 事件数据: {event_data}")
                import traceback
                console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
        
        async def safe_handle_navigation(event_data):
            try:
                step_counter['count'] += 1
                console.print(f"🌐 收到导航事件 - 步骤 {step_counter['count']}: {event_data}")
                await self._record_operation('navigation', event_data, step_counter['count'])
                console.print(f"✅ 导航事件处理完成 - 步骤 {step_counter['count']}")
            except Exception as e:
                console.print(f"❌ 处理导航事件失败: {e}")
                console.print(f"❌ 事件数据: {event_data}")
                import traceback
                console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
        
        async def safe_handle_element_selection(event_data):
            try:
                console.print(f"🎯 收到元素选择事件: {event_data}")
                # 设置元素选择模式标志，避免后续点击被记录
                self.element_selection_mode = True
                self.selected_element = event_data
                console.print("📸 准备拍摄选中元素截图并结束录制...")
                
                # 拍摄选中元素的高亮截图
                console.print("🔄 正在执行截图...")
                try:
                    await self._take_selected_element_screenshot(event_data)
                    console.print("✅ 选中元素截图已完成")
                    
                    # 延迟1秒确保截图文件写入完成
                    console.print("⏱️  等待1秒确保截图文件保存...")
                    await asyncio.sleep(1.0)
                    console.print("✅ 截图保存等待完成")
                    
                except Exception as screenshot_error:
                    console.print(f"❌ 截图失败: {screenshot_error}")
                    import traceback
                    console.print(f"❌ 截图错误堆栈: {traceback.format_exc()}")
                    
                    # 即使截图失败也继续结束录制
                    console.print("⚠️  截图失败，但继续结束录制")
                
                # 截图完成后再结束录制
                console.print("🛑 现在开始关闭录制...")
                self.recording_interrupted = True
                console.print("✅ 录制中断标志已设置，录制即将结束")
                
            except Exception as e:
                console.print(f"❌ 处理元素选择失败: {e}")
                import traceback
                console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
                
                # 即使处理失败也要设置中断标志，避免录制卡住
                console.print("⚠️  元素选择处理失败，但设置录制中断标志以结束录制")
                self.recording_interrupted = True
        
        async def safe_handle_element_selection_mode_start(event_data):
            try:
                console.print("🎯 用户按下快捷键，进入元素选择模式")
                self.element_selection_mode = True
                console.print("✅ 元素选择模式已启用，后续点击将不被记录")
            except Exception as e:
                console.print(f"❌ 处理元素选择模式启动失败: {e}")
        
        # 注册事件处理器（暂时只监听点击和输入）
        try:
            console.print("🔗 开始设置事件处理器...")
            await self.event_listener.setup_listeners(
                self.page,
                on_click=safe_handle_click,
                on_input=safe_handle_input,
                on_navigation=None,  # 暂时禁用导航事件避免冲突
                on_element_selection=safe_handle_element_selection,
                on_element_selection_mode_start=safe_handle_element_selection_mode_start,
                recorder=self  # 传递recorder实例供移除遮罩使用
            )
            console.print("✅ 事件处理器设置完成")
            console.print(f"📊 当前operations数量: {len(self.operations)}")
        except Exception as e:
            console.print(f"❌ 事件监听器设置失败: {e}")
            console.print(f"❌ 错误类型: {type(e).__name__}")
            import traceback
            console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
            raise  # 重新抛出错误让上层处理
    
    async def _record_operation(self, action: str, event_data: Dict, step_id: int):
        """记录操作（带锁）。返回已追加的operation字典。"""
        async with self._record_operation_semaphore:
            return await self._record_operation_core(action, event_data, step_id)

    async def _record_operation_core(self, action: str, event_data: Dict, step_id: int) -> Dict[str, Any]:
        """记录操作的核心逻辑（不加锁），便于复用/组合。返回追加到self.operations的operation。"""
        console.print(f"📝 开始记录操作: {action} (步骤 {step_id})")
        try:
            timestamp = datetime.now().isoformat()
            
            # 验证输入参数
            if not isinstance(event_data, dict):
                console.print(f"⚠️  event_data不是字典类型: {type(event_data)}, 值: {event_data}")
                event_data = {'error': 'invalid_event_data', 'type': str(type(event_data))}
            
            # 获取页面截图
            screenshot_path = f"screenshots/step_{step_id}.png"
            full_screenshot_path = self.session_dir / screenshot_path
            
            console.print(f"📷 准备截图到: {full_screenshot_path}")
            console.print(f"🎯 目标选择器: {event_data.get('selector', 'N/A')}")
            
            try:
                # 基本页面状态检查
                if not self.page:
                    raise Exception("页面对象不存在")
                
                console.print(f"🚀 跳过页面状态检查，直接进行截图: {event_data.get('selector', '')}")
                
                # 高亮截图功能
                console.print(f"⏳ 等待截图锁并进行截图: {event_data.get('selector', '')}")
                screenshot_success = False
                try:
                    # 添加超时避免无限等待
                    await asyncio.wait_for(
                        self._take_highlighted_screenshot(full_screenshot_path, event_data.get('selector', '')),
                        timeout=10.0
                    )
                    screenshot_success = True
                    console.print(f"✅ 截图操作完成: {event_data.get('selector', '')}")
                except asyncio.TimeoutError:
                    console.print(f"⏰ 截图操作超时: {event_data.get('selector', '')}")
                    console.print(f"📝 截图超时，但继续记录操作: {action}")
                    # 不抛出异常，让操作记录继续
                except Exception as screenshot_err:
                    console.print(f"❌ 截图过程异常: {screenshot_err}")
                    console.print(f"📝 截图异常，但继续记录操作: {action}")
                    # 不抛出异常，让操作记录继续
                
                # 强制检查截图文件是否真正创建了
                if not screenshot_success or not full_screenshot_path.exists():
                    console.print(f"🔍 检测到截图未完成或文件不存在: {full_screenshot_path.name}")
                    console.print(f"📝 可能被页面导航中断，将screenshot路径设为null以避免引用失效文件")
                    screenshot_path = None  # 设置为None避免引用不存在的文件
                    console.print(f"🔄 截图失败但operation记录将继续进行")
                
            except Exception as e:
                console.print(f"⚠️  截图失败: {e}")
                screenshot_path = None
            
            # 捕获DOM上下文：优先使用事件自带的element_snapshot，避免导航后错位
            dom_context = {'error': 'not_captured', 'selector': event_data.get('selector', '')}
            try:
                snapshot = event_data.get('element_snapshot') if isinstance(event_data, dict) else None
                if snapshot and isinstance(snapshot, dict):
                    dom_context = snapshot
                elif hasattr(self, 'context_capturer') and self.context_capturer:
                    selector_to_use = event_data.get('selector', '')
                    robust_selector = event_data.get('robust_selector')
                    if robust_selector:
                        selector_to_use = robust_selector
                    dom_context = await self.context_capturer.capture_element_context(
                        self.page, 
                        selector_to_use
                    )
                else:
                    console.print("⚠️  context_capturer未初始化")
                    
            except Exception as e:
                console.print(f"⚠️  DOM上下文捕获失败: {e}")
                console.print(f"⚠️  错误类型: {type(e).__name__}")
                dom_context = {'error': str(e), 'selector': event_data.get('selector', '')}
            
            # 安全地获取页面信息
            page_url = 'unknown'
            viewport = {'width': 1280, 'height': 720}
            
            try:
                if self.page:
                    page_url = self.page.url
                    viewport_size = self.page.viewport_size
                    if viewport_size:
                        viewport = viewport_size
            except Exception as e:
                console.print(f"⚠️  获取页面信息失败: {e}")
                console.print(f"⚠️  页面对象类型: {type(self.page)}")
            
            operation = {
                'step_id': step_id,
                'timestamp': timestamp,
                'action': action,
                'selector': event_data.get('selector', ''),
                'value': event_data.get('value', ''),
                'text_content': event_data.get('text_content', ''),
                'screenshot': screenshot_path,
                'dom_context': dom_context,
                'page_url': page_url,
                'viewport': viewport
            }
            
            self.operations.append(operation)
            console.print(f"✅ 操作记录完成 {step_id}: {action} - {event_data.get('selector', 'N/A')}")
            console.print(f"📊 当前operations总数: {len(self.operations)}")
            return operation
            
        except Exception as e:
            console.print(f"❌ _record_operation_core失败: {e}")
            console.print(f"❌ 错误类型: {type(e).__name__}")
            console.print(f"❌ action: {action}, step_id: {step_id}")
            console.print(f"❌ event_data类型: {type(event_data)}, 内容: {event_data}")
            import traceback
            console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
            
            # 即使失败也要记录基本信息避免程序崩溃
            try:
                operation = {
                    'step_id': step_id,
                    'timestamp': datetime.now().isoformat(),
                    'action': action,
                    'error': str(e),
                    'event_data_type': str(type(event_data)),
                    'event_data_str': str(event_data)[:200]
                }
                self.operations.append(operation)
                console.print(f"🔧 fallback操作记录完成")
                return operation
            except Exception as fallback_error:
                console.print(f"❌ 连fallback记录都失败了: {fallback_error}")
                raise

    def _remove_screenshot_file(self, screenshot_relative_path: Optional[str]):
        """删除相对路径的截图文件（如果存在）。"""
        try:
            if not screenshot_relative_path:
                return
            if not self.session_id:
                return
            session_dir = self.session_dir
            full_path = session_dir / screenshot_relative_path
            if full_path.exists():
                full_path.unlink()
                console.print(f"🗑️  已删除旧截图: {full_path}")
        except Exception as e:
            console.print(f"⚠️  删除截图失败: {e}")

    async def _delete_operation_by_step_id(self, step_id: int):
        """按step_id删除已记录的operation并清理其截图。"""
        try:
            index_to_remove = None
            op_to_remove = None
            for idx, op in enumerate(self.operations):
                if op.get('step_id') == step_id:
                    index_to_remove = idx
                    op_to_remove = op
                    break
            if index_to_remove is None:
                console.print(f"ℹ️  未找到需要删除的operation: step_id={step_id}")
                return
            # 清理截图
            self._remove_screenshot_file(op_to_remove.get('screenshot'))
            # 从列表移除
            self.operations.pop(index_to_remove)
            console.print(f"🗑️  已删除旧operation: step_id={step_id}")
        except Exception as e:
            console.print(f"⚠️  删除operation失败: {e}")

    def _cancel_pending_flush_for_selector(self, selector: str):
        """取消并清理某选择器的遗留输入合并任务。"""
        try:
            pending_op = self.pending_input_operations.get(selector)
            if not pending_op:
                return
            flush_task = pending_op.get('flush_task')
            if flush_task and not flush_task.done():
                flush_task.cancel()
                console.print(f"🚫 已取消遗留的输入合并任务: {selector}")
        except Exception as e:
            console.print(f"⚠️  取消遗留合并任务失败: {e}")
        finally:
            if selector in self.pending_input_operations:
                self.pending_input_operations.pop(selector, None)

    async def _record_input_with_replacement(self, event_data: Dict, step_id: int):
        """输入事件采用替换模式：先保存当前输入；如同一selector后续再输入，则删除上一条输入记录及截图。"""
        selector = event_data.get('selector', '')
        # 统一串行化，避免与其他事件竞争
        async with self._record_operation_semaphore:
            # 先取消遗留的合并任务，避免异步flush再次写入旧记录
            try:
                if selector:
                    self._cancel_pending_flush_for_selector(selector)
            except Exception as e:
                console.print(f"⚠️  取消遗留合并任务时出错: {e}")
            prev = self.last_input_by_selector.get(selector)
            # 先记录当前输入
            current_op = await self._record_operation_core('input', event_data, step_id)
            # 删除上一条同selector的输入（如果存在且不是当前）
            try:
                if prev and isinstance(prev.get('step_id'), int) and prev['step_id'] != step_id:
                    await self._delete_operation_by_step_id(prev['step_id'])
            finally:
                # 更新最新映射
                self.last_input_by_selector[selector] = {
                    'step_id': step_id,
                    'screenshot': current_op.get('screenshot')
                }
    
    
    async def _save_session_data(self, session_dir: Path, name: str, url: str):
        """保存会话数据"""
        # 使用缓存的页面标题，避免在页面关闭后访问
        page_title = self.cached_page_title or 'Unknown'
        
        # 收集访问的页面URL
        pages_visited = list(set([op.get('page_url', '') for op in self.operations if op.get('page_url')]))
        
        # 计算会话持续时间
        if self.operations:
            first_timestamp = self.operations[0].get('timestamp', '')
            last_timestamp = self.operations[-1].get('timestamp', '')
            try:
                from datetime import datetime as dt
                first_time = dt.fromisoformat(first_timestamp)
                last_time = dt.fromisoformat(last_timestamp)
                duration = (last_time - first_time).total_seconds()
            except:
                duration = 0
        else:
            duration = 0
        
        session_data = {
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'metadata': {
                'name': name,
                'url': url,
                'title': page_title,
                'browser': 'chromium',
                'viewport': {'width': 1920, 'height': 1080}
            },
            'statistics': {
                'total_operations': len(self.operations),
                'total_screenshots': len([op for op in self.operations if op.get('screenshot')]),
                'session_duration_seconds': round(duration, 2),
                'pages_visited': pages_visited
            },
            'return_reference_element': self._build_return_element_data() if self.selected_element else None,
            'ai_analysis': {
                'analyzed': False,
                'analysis_timestamp': None,
                'suggested_parameters': [],
                'function_signature': None
            }
        }
        
        # 保存元数据
        metadata_path = session_dir / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        
        # 保存操作记录
        operations_path = session_dir / 'operations.json'
        with open(operations_path, 'w', encoding='utf-8') as f:
            json.dump(self.operations, f, ensure_ascii=False, indent=2)
        
        console.print(f"💾 会话数据已保存到: {session_dir}")
    
    def _validate_url(self, url: str) -> str:
        """验证并修复URL格式"""
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
    
    async def _handle_merged_input(self, action: str, event_data: Dict, step_id: int):
        """输入替换模式：每次输入立即保存，并删除同一selector上一条输入的记录与截图。"""
        try:
            selector = event_data.get('selector', '')
            value = event_data.get('value', '')
            console.print(f"🎯 立即保存输入事件: '{value}' (选择器: {selector}, 步骤: {step_id})")
            if not selector:
                # 没有选择器时直接记录
                console.print("⚠️  没有选择器，直接记录输入操作")
                await self._record_operation(action, event_data, step_id)
                return
            # 替换策略
            await self._record_input_with_replacement(event_data, step_id)
            console.print(f"✅ 输入事件保存完成 - 替换同元素旧记录: {selector}")
        except Exception as e:
            console.print(f"❌ 输入替换模式处理失败: {e}")
            console.print(f"❌ 事件数据: {event_data}")
            import traceback
            console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
            # 回退到直接记录
            try:
                await self._record_operation(action, event_data, step_id)
            except Exception as final_error:
                console.print(f"❌ 回退记录仍失败: {final_error}")
    
    async def _flush_pending_input(self, selector: str, delay: float):
        """延迟刷新待处理的输入操作"""
        try:
            await asyncio.sleep(delay)
            await self._flush_pending_input_immediate(selector)
        except asyncio.CancelledError:
            console.print(f"🚫 输入刷新任务被取消: {selector}")
    
    async def _flush_pending_input_immediate(self, selector: str):
        """立即刷新待处理的输入操作"""
        if selector not in self.pending_input_operations:
            console.print(f"⚠️  选择器 {selector} 不在待处理操作中，跳过")
            return
        
        try:
            # 取出待处理操作并立即从字典中删除，避免竞争条件
            pending_op = self.pending_input_operations.pop(selector, None)
            if not pending_op:
                console.print(f"⚠️  选择器 {selector} 对应的操作为空，跳过")
                return
                
            event_data = pending_op['event_data']
            step_id = pending_op['step_id']
            
            console.print(f"💾 保存最终输入: '{event_data.get('value', '')}' (选择器: {selector})")
            
            # 取消可能还在运行的延迟任务
            if 'flush_task' in pending_op and not pending_op['flush_task'].done():
                pending_op['flush_task'].cancel()
                console.print(f"🚫 取消延迟刷新任务: {selector}")
            
            # 记录最终的输入操作
            console.print(f"🔄 开始记录输入操作: {selector}")
            await self._record_operation('input', event_data, step_id)
            console.print(f"✅ 输入操作记录完成: {selector}")
            
        except Exception as e:
            console.print(f"❌ 刷新输入操作失败: {e}")
            console.print(f"❌ 选择器: {selector}")
            console.print(f"❌ 当前待处理操作: {list(self.pending_input_operations.keys())}")
            import traceback
            console.print(f"❌ 错误详情: {traceback.format_exc()}")
    
    async def _flush_all_pending_inputs(self):
        """刷新所有待处理的输入操作"""
        console.print(f"🔄 刷新所有待处理输入 ({len(self.pending_input_operations)} 个)")
        
        # 复制键列表避免在迭代时修改字典
        selectors = list(self.pending_input_operations.keys())
        
        for selector in selectors:
            await self._flush_pending_input_immediate(selector)
    
    async def _monitor_html_changes(self):
        """智能HTML监控 - 1秒定时 + 变化检测"""
        last_url = None
        consecutive_same_count = 0
        
        console.print("🔍 开始监控HTML变化...")
        
        while not self.recording_interrupted:
            try:
                if not self.page:
                    break
                    
                current_url = self.page.url
                current_html = await self.page.content()
                current_time = datetime.now().isoformat()
                
                # 计算HTML内容哈希
                content_hash = hashlib.md5(current_html.encode()).hexdigest()
                
                # URL变化时立即记录
                if current_url != last_url:
                    console.print(f"🌐 URL变化: {current_url[:70]}...")
                    consecutive_same_count = 0
                    last_url = current_url
                    
                    # 强制记录新URL
                    self._update_html_cache(current_url, current_html, current_time, content_hash)
                    
                else:
                    # 同一URL，检查内容是否变化
                    existing_data = self.html_cache.get(current_url, {})
                    if existing_data.get('content_hash') != content_hash:
                        console.print(f"📝 内容更新: {current_url[:50]}...")
                        self._update_html_cache(current_url, current_html, current_time, content_hash)
                        consecutive_same_count = 0
                    else:
                        consecutive_same_count += 1
                        
                        # 内容长时间无变化时降低检查频率
                        if consecutive_same_count > 10:  # 10秒无变化
                            await asyncio.sleep(2.0)      # 降低到3秒检查一次
                            consecutive_same_count = 8    # 重置计数避免无限增长
                            continue
                
                await asyncio.sleep(1.0)  # 正常1秒检查间隔
                
            except Exception as e:
                console.print(f"⚠️  HTML监控异常: {e}")
                await asyncio.sleep(1.0)

    def _update_html_cache(self, url: str, html: str, timestamp: str, content_hash: str):
        """更新HTML缓存"""
        self.html_cache[url] = {
            'html': html,
            'last_updated': timestamp,
            'content_hash': content_hash,
            'size_kb': len(html.encode()) // 1024
        }
        
        # 更新URL时间线
        if not self.url_timeline or self.url_timeline[-1]['url'] != url:
            self.url_timeline.append({
                'url': url,
                'timestamp': timestamp,
                'title': self.cached_page_title or 'Unknown'
            })

    async def _take_highlighted_screenshot(self, screenshot_path: Path, selector: str):
        """高亮截图功能"""
        console.print(f"📸 开始高亮截图: selector='{selector}'")
        console.print(f"📁 截图将保存到: {screenshot_path}")
        
        # 防止并发截图冲突
        if not hasattr(self, '_screenshot_lock'):
            self._screenshot_lock = asyncio.Lock()
        
        screenshot_completed = False  # 追踪截图是否真正完成
        try:
            async with self._screenshot_lock:
                console.print(f"🔒 获取截图锁，开始处理: {selector}")
                if selector:
                    console.print(f"🎯 查找目标元素: {selector}")
                    # 检查页面状态和元素（更快的超时，更好的错误处理）
                    try:
                        # 首先快速检查页面是否还可访问
                        page_ready = await asyncio.wait_for(
                            self.page.evaluate("() => document.readyState"), 
                            timeout=0.3  # 300ms快速检查
                        )
                        console.print(f"📊 页面状态: {page_ready}")
                        
                        # 如果页面可访问，再检查元素
                        element_exists = await asyncio.wait_for(
                            self.page.evaluate(f"""
                        () => {{
                        const selector = '{selector}';
                        const element = document.querySelector(selector);
                        return element ? {{
                            exists: true,
                            tagName: element.tagName,
                            textContent: element.textContent?.trim().substring(0, 50),
                            visible: element.offsetParent !== null
                        }} : {{ exists: false }};
                    }}
                """), timeout=0.5)  # 500ms更快超时
                        console.print(f"🔍 元素检查结果: {element_exists}")
                    except asyncio.TimeoutError:
                        console.print(f"⏰ 页面状态或元素查找超时 - 页面可能正在导航: {selector}")
                        element_exists = {'exists': False}
                    except Exception as eval_error:
                        console.print(f"❌ 页面访问失败 - 页面导航中断: {eval_error}")
                        console.print(f"❌ 错误类型: {type(eval_error).__name__}")
                        element_exists = {'exists': False}
                else:
                    element_exists = {'exists': False}
                
                if element_exists.get('exists'):
                    console.print("✨ 添加高亮效果和元素信息...")
                    # 高亮目标元素并添加信息标签（添加超时）
                    try:
                        await asyncio.wait_for(self.page.evaluate(f"""
                        () => {{
                            const selector = '{selector}';
                            const element = document.querySelector(selector);
                            if (element) {{
                                // 添加高亮样式
                                element.style.outline = '3px solid #ff4444';
                                element.style.outlineOffset = '2px';
                                element.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                element.style.boxShadow = '0 0 10px rgba(255, 68, 68, 0.8)';
                                element.style.zIndex = '9999';
                                
                                // 确保元素可见（滚动到视图中）
                                element.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                                
                                // 创建信息提示框
                                const infoBox = document.createElement('div');
                                infoBox.id = 'webautomation-info-box';
                                infoBox.style.cssText = `
                                    position: fixed;
                                    top: 10px;
                                    right: 10px;
                                    background: rgba(0, 0, 0, 0.9);
                                    color: #fff;
                                    padding: 12px;
                                    border-radius: 8px;
                                    font-family: monospace;
                                    font-size: 12px;
                                    line-height: 1.4;
                                    z-index: 99999;
                                    max-width: 400px;
                                    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                                    border: 2px solid #ff4444;
                                `;
                                
                                // 收集元素信息
                                const tagName = element.tagName.toLowerCase();
                                const id = element.id || 'N/A';
                                const className = element.className || 'N/A';
                                const textContent = (element.textContent || '').trim().substring(0, 50);
                                const elementType = element.type || 'N/A';
                                const name = element.name || 'N/A';
                                
                                // 构建信息内容
                                let infoContent = `
                                    <div style="color: #ff6666; font-weight: bold; margin-bottom: 8px;">🎯 元素信息</div>
                                    <div><span style="color: #66ff66;">标签:</span> &lt;${{tagName}}&gt;</div>
                                    <div><span style="color: #66ff66;">ID:</span> ${{id}}</div>
                                    <div><span style="color: #66ff66;">Class:</span> ${{className}}</div>
                                `;
                                
                                if (elementType !== 'N/A') {{
                                    infoContent += `<div><span style="color: #66ff66;">Type:</span> ${{elementType}}</div>`;
                                }}
                                
                                if (name !== 'N/A') {{
                                    infoContent += `<div><span style="color: #66ff66;">Name:</span> ${{name}}</div>`;
                                }}
                                
                                if (textContent) {{
                                    infoContent += `<div><span style="color: #66ff66;">Text:</span> ${{textContent}}${{textContent.length === 50 ? '...' : ''}}</div>`;
                                }}
                                
                                infoContent += `
                                    <div style="margin-top: 8px; color: #ffff66;">选择器: ${{selector}}</div>
                                `;
                                
                                infoBox.innerHTML = infoContent;
                                document.body.appendChild(infoBox);
                            }}
                        }}
                    """), timeout=1.0)  # 1秒超时
                        console.print("✅ 高亮效果添加成功")
                    except asyncio.TimeoutError:
                        console.print(f"⏰ 高亮效果添加超时: {selector}")
                    except Exception as highlight_error:
                        console.print(f"❌ 高亮效果添加失败: {highlight_error}")
                    
                    console.print("⏱️  等待高亮效果...")
                    await asyncio.sleep(0.5)  # 等待高亮效果和滚动完成
                
                console.print(f"📷 开始截图到: {screenshot_path}")
                # 截图（添加超时）
                try:
                    await asyncio.wait_for(
                        self.page.screenshot(path=str(screenshot_path)), 
                        timeout=3
                    )
                    screenshot_completed = True  # 标记截图成功完成
                    console.print("✅ 截图完成")
                except asyncio.TimeoutError:
                    console.print(f"⏰ 截图操作超时: {screenshot_path}")
                    console.print(f"📝 页面可能正在导航，跳过截图但继续记录操作")
                    # 不返回，让函数继续执行到清理阶段
                except Exception as screenshot_error:
                    console.print(f"❌ 截图操作失败: {screenshot_error}")
                    console.print(f"📝 截图失败但继续记录操作: {type(screenshot_error).__name__}")
                    # 不返回，让函数继续执行到清理阶段
                
                if element_exists.get('exists'):
                    console.print("🧹 清理高亮效果和信息框...")
                    # 移除高亮和信息框（添加超时）
                    try:
                        await asyncio.wait_for(self.page.evaluate(f"""
                            () => {{
                                const selector = '{selector}';
                                const element = document.querySelector(selector);
                                if (element) {{
                                    element.style.outline = '';
                                    element.style.outlineOffset = '';
                                    element.style.backgroundColor = '';
                                    element.style.boxShadow = '';
                                    element.style.zIndex = '';
                                }}
                                
                                // 删除信息提示框
                                const infoBox = document.getElementById('webautomation-info-box');
                                if (infoBox) {{
                                    infoBox.remove();
                                }}
                            }}
                        """), timeout=1.0)  # 1秒超时
                        console.print("✅ 高亮效果清理成功")
                    except asyncio.TimeoutError:
                        console.print(f"⏰ 高亮效果清理超时: {selector}")
                    except Exception as cleanup_error:
                        console.print(f"❌ 高亮效果清理失败: {cleanup_error}")
                else:
                    console.print("📷 无选择器，使用普通截图")
                    # 没有选择器时使用普通截图（添加超时）
                    try:
                        await asyncio.wait_for(
                            self.page.screenshot(path=str(screenshot_path)),
                            timeout=3
                        )
                        console.print("✅ 普通截图完成")
                    except asyncio.TimeoutError:
                        console.print(f"⏰ 普通截图超时: {screenshot_path}")
                        console.print(f"📝 页面可能正在导航，跳过普通截图但继续记录操作")
                        # 不返回，让函数继续执行到清理阶段
                    except Exception as screenshot_error:
                        console.print(f"❌ 普通截图失败: {screenshot_error}")
                        console.print(f"📝 普通截图失败但继续记录操作: {type(screenshot_error).__name__}")
                        # 不返回，让函数继续执行到清理阶段
                    
        except Exception as e:
            console.print(f"❌ 高亮截图失败: {e}")
            console.print(f"❌ 错误类型: {type(e).__name__}")
            import traceback
            console.print(f"❌ 错误堆栈: {traceback.format_exc()}")
        
            # 失败时使用普通截图
            try:
                console.print("🔄 尝试普通截图作为备用方案...")
                await self.page.screenshot(path=str(screenshot_path))
                console.print("✅ 备用截图成功")
            except Exception as e2:
                console.print(f"❌ 备用截图也失败: {e2}")
                console.print(f"❌ 页面状态: url={self.page.url if self.page else 'None'}")
                console.print(f"❌ 截图路径: {screenshot_path}")
                console.print(f"📝 所有截图方案都失败，但继续记录操作")
                # 不再抛出异常，让操作记录继续
                
            console.print(f"🔓 释放截图锁: {selector}")
                
        finally:
            # 无论如何都要确保释放截图完成状态被正确报告
            if not screenshot_completed:
                console.print(f"⚠️  截图过程被中断或失败: {selector}")
                console.print(f"📝 截图状态: 未完成，但操作将继续记录")
            else:
                console.print(f"✅ 截图流程完整完成: {selector}")

    async def _save_html_cache(self, session_dir: Path):
        """批量保存HTML缓存 - 优化版本"""
        if not self.html_cache:
            console.print("ℹ️  没有HTML缓存数据需要保存")
            return
            
        html_dir = session_dir / 'html_snapshots'
        html_dir.mkdir(exist_ok=True)
        
        console.print(f"💾 正在保存 {len(self.html_cache)} 个URL的HTML快照...")
        
        # 并发写入HTML文件
        write_tasks = []
        url_mapping = {}
        
        for i, (url, html_data) in enumerate(self.html_cache.items()):
            safe_filename = self._url_to_filename(url, i)
            html_file = html_dir / f"{safe_filename}.html"
            
            # 创建写入任务
            write_task = self._write_html_file(html_file, url, html_data)
            write_tasks.append(write_task)
            
            # 构建映射信息
            url_mapping[url] = {
                'filename': safe_filename + '.html',
                'last_updated': html_data['last_updated'],
                'content_hash': html_data['content_hash'],
                'size_kb': html_data.get('size_kb', 0)
            }
        
        # 并发执行所有写入任务
        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)
        
        # 保存元数据
        await self._save_html_metadata(html_dir, url_mapping)
        
        console.print(f"✅ HTML快照保存完成: {html_dir}")

    async def _write_html_file(self, html_file: Path, url: str, html_data: dict):
        """异步写入单个HTML文件"""
        try:
            # 清理HTML，只保留选择器定位需要的内容
            cleaned_html = self._clean_html_for_storage(html_data['html'])
            
            # 计算清理后的大小
            cleaned_size_kb = len(cleaned_html.encode()) // 1024
            original_size_kb = html_data.get('size_kb', 0)
            compression_ratio = round((1 - cleaned_size_kb / max(original_size_kb, 1)) * 100, 1) if original_size_kb > 0 else 0
            
            html_content = f"""<!--
=== 网页自动化HTML快照 (已清理) ===
URL: {url}
最后更新: {html_data['last_updated']}
原始大小: {original_size_kb} KB
清理后大小: {cleaned_size_kb} KB
压缩率: {compression_ratio}%
生成时间: {datetime.now().isoformat()}

清理说明:
- 已删除: <script>、<style>、<noscript> 标签
- 已删除: style属性、onclick等事件属性
- 已删除: CSS样式定义
- 保留: id、class、name、type等选择器属性
- 保留: 文本内容和DOM结构
-->
<!DOCTYPE html>
{cleaned_html}"""
            
            # 使用同步写入（避免aiofiles依赖）
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
        except Exception as e:
            console.print(f"⚠️  写入HTML文件失败 {html_file}: {e}")

    def _clean_html_for_storage(self, html: str) -> str:
        """使用BeautifulSoup清理HTML，只保留选择器定位需要的内容"""
        try:
            from bs4 import BeautifulSoup
            import re
            import html as html_module
            
            console.print(f"🧹 开始清理HTML（使用BeautifulSoup），原始大小: {len(html.encode()) // 1024} KB")
            
            # 首先解码所有HTML实体编码 (&lt; &gt; &amp; &quot; 等)
            console.print("🔄 预处理: 解码HTML实体编码...")
            decoded_html = html_module.unescape(html)
            console.print(f"📏 解码后大小: {len(decoded_html.encode()) // 1024} KB")
            
            # 使用BeautifulSoup解析解码后的HTML
            soup = BeautifulSoup(decoded_html, 'html.parser')
            
            # 1. 删除<script>标签及其内容
            for script in soup.find_all('script'):
                script.decompose()
            
            # 2. 删除<style>标签及其内容
            for style in soup.find_all('style'):
                style.decompose()
                
            # 3. 删除<noscript>标签及其内容
            for noscript in soup.find_all('noscript'):
                noscript.decompose()
            
            # 4. 删除注释
            from bs4 import Comment
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
            
            # 5. 删除所有元素的style属性
            for element in soup.find_all():
                if element.get('style'):
                    del element['style']
            
            # 6. 删除事件属性 (onclick, onload, onmouseover等)
            event_attrs = ['onclick', 'onload', 'onmouseover', 'onmouseout', 'onmousedown', 'onmouseup', 
                          'onfocus', 'onblur', 'onchange', 'onsubmit', 'onreset', 'onkeydown', 'onkeyup', 
                          'onkeypress', 'ondblclick', 'oncontextmenu', 'oninput', 'onscroll']
            
            for element in soup.find_all():
                for event_attr in event_attrs:
                    if element.get(event_attr):
                        del element[event_attr]
            
            # 7. 删除不重要的属性但保留选择器相关属性（id, class, name, type等）
            unwanted_attrs = ['width', 'height', 'border', 'cellpadding', 'cellspacing', 
                             'bgcolor', 'background', 'color', 'face', 'size']
            
            for element in soup.find_all():
                for attr in unwanted_attrs:
                    if element.get(attr):
                        del element[attr]
            
            # 8. 简化src和href属性，只保留文件名部分
            for element in soup.find_all(['img', 'script', 'link', 'a']):
                for attr in ['src', 'href']:
                    if element.get(attr):
                        original_value = element[attr]
                        if '/' in original_value:
                            filename = original_value.split('/')[-1]
                            element[attr] = f"...{filename}"
            
            # 转换回字符串
            cleaned_html = str(soup)
            
            # 10. 压缩多余的空白字符
            cleaned_html = re.sub(r'\s+', ' ', cleaned_html)
            cleaned_html = re.sub(r'>\s+<', '><', cleaned_html)
            
            # 11. 清理空行
            cleaned_html = re.sub(r'\n\s*\n', '\n', cleaned_html)
            
            cleaned_size_kb = len(cleaned_html.encode()) // 1024
            original_size_kb = len(html.encode()) // 1024
            compression_ratio = round((1 - cleaned_size_kb / max(original_size_kb, 1)) * 100, 1) if original_size_kb > 0 else 0
            
            console.print(f"✅ BeautifulSoup HTML清理完成")
            console.print(f"📊 原始大小: {original_size_kb} KB → 清理后: {cleaned_size_kb} KB (压缩率: {compression_ratio}%)")
            
            return cleaned_html.strip()
            
        except Exception as e:
            console.print(f"⚠️  BeautifulSoup HTML清理失败: {e}")
            console.print("🔄 回退到正则表达式清理方案...")
            
            # 回退到正则表达式方案
            try:
                import re
                
                # 简化版本的正则清理
                html = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html, flags=re.IGNORECASE | re.DOTALL)
                html = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html, flags=re.IGNORECASE | re.DOTALL)
                html = re.sub(r'<noscript\b[^<]*(?:(?!<\/noscript>)<[^<]*)*<\/noscript>', '', html, flags=re.IGNORECASE | re.DOTALL)
                html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
                html = re.sub(r'\s+style\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
                
                return html.strip()
            except Exception as e2:
                console.print(f"⚠️  正则表达式清理也失败: {e2}")
                return html

    async def _save_html_metadata(self, html_dir: Path, url_mapping: dict):
        """保存HTML元数据"""
        metadata = {
            'session_info': {
                'total_urls': len(url_mapping),
                'total_size_kb': sum(data.get('size_kb', 0) for data in url_mapping.values()),
                'recording_start': self.url_timeline[0]['timestamp'] if self.url_timeline else None,
                'recording_end': datetime.now().isoformat()
            },
            'url_mapping': url_mapping,
            'url_timeline': self.url_timeline,
            'usage_tips': {
                'description': '此目录包含录制过程中访问的所有URL的最终HTML快照',
                'file_format': '文件名格式: {序号}_{域名}_{路径}.html',
                'timeline': 'url_timeline记录了页面访问的时间顺序',
                'debugging': '可用于调试选择器失效问题和分析页面结构变化'
            }
        }
        
        metadata_file = html_dir / 'metadata.json'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def _url_to_filename(self, url: str, index: int) -> str:
        """将URL转换为安全的文件名"""
        import re
        from urllib.parse import urlparse
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('.', '_')
            path = re.sub(r'[^\w\-_]', '_', parsed.path)
            
            # 限制文件名长度
            safe_name = f"{index:03d}_{domain}{path}"[:50]
            return safe_name
        except Exception:
            # URL解析失败时使用简单格式
            return f"{index:03d}_unknown_url"

    async def _take_selected_element_screenshot(self, element_data: Dict):
        """拍摄选中元素的高亮截图"""
        try:
            console.print(f"🎯 开始拍摄选中元素截图 - 数据: {element_data}")
            
            # 检查页面状态
            if not self.page:
                raise Exception("页面对象不存在")
            
            # 检查会话ID
            if not self.session_id:
                raise Exception("会话ID不存在")
                
            session_dir = self.session_dir
            screenshot_path = session_dir / 'selected_element_highlight.png'
            selector = element_data.get('selector', '')
            
            console.print(f"📸 拍摄选中元素截图: {selector}")
            console.print(f"📁 截图路径: {screenshot_path}")
            
            # 验证页面仍然活跃
            try:
                current_url = self.page.url
                console.print(f"🌐 当前页面URL: {current_url}")
            except Exception as e:
                console.print(f"⚠️  无法获取页面URL: {e}")
                raise Exception(f"页面可能已关闭: {e}")
            
            # 重新高亮选中的元素（使用不同的颜色）
            console.print(f"🎨 开始高亮选中元素: {selector}")
            # 安全地传递选择器，避免JavaScript注入
            await self.page.evaluate("""
                (selector) => {
                    const element = document.querySelector(selector);
                    if (!element) return;

                    // 注入强可见样式（使用!important避免被页面覆盖）
                    const stylesId = 'webautomation-force-visible-styles';
                    if (!document.getElementById(stylesId)) {
                        const styles = document.createElement('style');
                        styles.id = stylesId;
                        styles.textContent = `
                            [data-webautomation-force-visible] {
                                outline: 4px solid #28a745 !important;
                                outline-offset: 3px !important;
                                background-color: rgba(40, 167, 69, 0.15) !important;
                                box-shadow: 0 0 15px rgba(40, 167, 69, 0.6) !important;
                                position: relative !important;
                                visibility: visible !important;
                                opacity: 1 !important;
                                display: inline-block !important;
                                pointer-events: auto !important;
                                transform: none !important;
                                filter: none !important;
                                z-index: 2147483647 !important;
                            }
                            [data-webautomation-unhide] {
                                visibility: visible !important;
                                opacity: 1 !important;
                                display: block !important;
                                max-height: none !important;
                                height: auto !important;
                                overflow: visible !important;
                                clip: auto !important;
                                transform: none !important;
                            }
                            #webautomation-selected-rect {
                                position: fixed; border: 4px solid #28a745; background: rgba(40,167,69,0.08);
                                box-shadow: 0 0 20px rgba(40,167,69,0.6); z-index: 2147483647; pointer-events: none;
                            }
                        `;
                        document.head.appendChild(styles);
                    }

                    // 展开祖先节点避免隐藏
                    const ancestors = [];
                    let p = element.parentElement;
                    while (p && p !== document.body) { ancestors.push(p); p = p.parentElement; }
                    ancestors.forEach(a => a.setAttribute('data-webautomation-unhide', '1'));

                    // 滚动到视图中心
                    try { element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' }); } catch (_) {}

                    // 强制显示并高亮
                    element.setAttribute('data-webautomation-force-visible', '1');

                    // 若元素尺寸不可见，则启用克隆预览作为兜底
                    const rect = element.getBoundingClientRect();
                    const tooSmall = rect.width < 2 || rect.height < 2;
                    let cloneContainer = document.getElementById('webautomation-selected-clone');
                    if (tooSmall || element.offsetParent === null) {
                        if (!cloneContainer) {
                            cloneContainer = document.createElement('div');
                            cloneContainer.id = 'webautomation-selected-clone';
                            cloneContainer.style.cssText = `
                                position: fixed; top: 20px; right: 20px; max-width: 600px; max-height: 320px; overflow: auto;
                                background: #fff; color: #111; padding: 10px; border-radius: 8px; z-index: 2147483647;
                                border: 3px solid #28a745; box-shadow: 0 4px 25px rgba(0,0,0,0.35); font-family: system-ui, sans-serif; font-size: 12px;`;
                            const label = document.createElement('div');
                            label.textContent = 'Preview of selected element (cloned)';
                            label.style.cssText = 'margin-bottom:6px; font-weight:600; color:#28a745;';
                            cloneContainer.appendChild(label);
                            document.body.appendChild(cloneContainer);
                        } else {
                            // 清空旧内容但保留标题
                            while (cloneContainer.childNodes.length > 1) cloneContainer.removeChild(cloneContainer.lastChild);
                        }
                        const clone = element.cloneNode(true);
                        cloneContainer.appendChild(clone);
                    }

                    // 添加原位矩形高亮框（如果尺寸有效）
                    if (rect.width >= 2 && rect.height >= 2) {
                        let rectBox = document.getElementById('webautomation-selected-rect');
                        if (!rectBox) {
                            rectBox = document.createElement('div');
                            rectBox.id = 'webautomation-selected-rect';
                            document.body.appendChild(rectBox);
                        }
                        rectBox.style.left = rect.left + 'px';
                        rectBox.style.top = rect.top + 'px';
                        rectBox.style.width = rect.width + 'px';
                        rectBox.style.height = rect.height + 'px';
                    }

                    // 信息框
                    const infoBox = document.createElement('div');
                    infoBox.id = 'selected-element-info';
                    infoBox.style.cssText = `
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        background: rgba(40, 167, 69, 0.95);
                        color: white;
                        padding: 12px 14px;
                        border-radius: 10px;
                        font-family: monospace;
                        font-size: 12px;
                        line-height: 1.4;
                        z-index: 2147483647;
                        max-width: 460px;
                        box-shadow: 0 4px 25px rgba(0,0,0,0.3);
                        border: 3px solid #28a745;`;
                    const tagName = element.tagName.toLowerCase();
                    const id = element.id || 'N/A';
                    const className = element.className || 'N/A';
                    const textContent = (element.textContent || '').trim().substring(0, 80);
                    infoBox.innerHTML = `
                        <div style="color:#90ff90;font-weight:bold;margin-bottom:8px;font-size:13px;">✅ 已选中返回内容区域</div>
                        <div><span style=\"color:#c0ffc0;\">标签:</span> &lt;${tagName}&gt;</div>
                        <div><span style=\"color:#c0ffc0;\">ID:</span> ${id}</div>
                        <div><span style=\"color:#c0ffc0;\">Class:</span> ${className}</div>
                        ${textContent ? `<div><span style=\"color:#c0ffc0;\">Text:</span> ${textContent}${textContent.length === 80 ? '...' : ''}</div>` : ''}
                        <div style="margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.3);">
                            <div style="color: #ffff90; font-size: 11px;">选择器: ${selector}</div>
                        </div>
                        <div style="margin-top: 6px; font-size: 11px; color: #d0ffd0;">AI将从此区域提取目标数据</div>`;
                    document.body.appendChild(infoBox);
                }
            """, selector)
            
            # 等待高亮效果显示
            console.print("⏱️  等待高亮效果显示...")
            await asyncio.sleep(1.0)
            console.print("✅ 高亮效果显示完成")
            
            # 截图
            console.print("📷 开始执行页面截图...")
            await self.page.screenshot(path=str(screenshot_path))
            console.print(f"✅ 选中元素截图已保存: {screenshot_path.name}")
            
            # 验证截图文件是否真的被创建
            try:
                if screenshot_path.exists():
                    file_size = screenshot_path.stat().st_size
                    console.print(f"📁 截图文件验证成功: {screenshot_path.name} ({file_size} bytes)")
                else:
                    console.print(f"⚠️  截图文件不存在: {screenshot_path}")
            except Exception as verify_error:
                console.print(f"⚠️  截图文件验证失败: {verify_error}")
            
            # 清理高亮效果
            console.print("🧹 清理高亮效果...")
            await self.page.evaluate("""
                (selector) => {
                    const element = document.querySelector(selector);
                    if (element) {
                        element.removeAttribute('data-webautomation-force-visible');
                    }
                    // 清理祖先标记
                    document.querySelectorAll('[data-webautomation-unhide]')
                        .forEach(n => n.removeAttribute('data-webautomation-unhide'));
                    // 清理矩形/克隆/信息框/样式
                    const ids = ['webautomation-selected-rect','webautomation-selected-clone','selected-element-info'];
                    ids.forEach(id => { const el = document.getElementById(id); if (el) el.remove(); });
                    const styles = document.getElementById('webautomation-force-visible-styles');
                    if (styles) styles.remove();
                }
            """, selector)
            console.print("✅ 高亮效果清理完成")
            
            console.print("🎯 选中元素截图函数执行完毕")
            
        except Exception as e:
            console.print(f"❌ 选中元素截图失败: {e}")
            import traceback
            console.print(f"❌ 错误详情: {traceback.format_exc()}")
            raise  # 重新抛出异常让上层处理

    def _build_return_element_data(self) -> Dict:
        """构建返回元素数据结构"""
        if not self.selected_element:
            return None
        
        return {
            'description': '用户选择的包含目标内容的元素区域',
            'selector': self.selected_element.get('selector', ''),
            'screenshot': 'selected_element_highlight.png',
            'element_details': {
                'tag_name': self.selected_element.get('tagName', ''),
                'id': self.selected_element.get('id'),
                'class_name': self.selected_element.get('className'),
                'text_preview': self.selected_element.get('textContent', '')[:200] + ('...' if len(self.selected_element.get('textContent', '')) > 200 else ''),
                'selection_timestamp': self.selected_element.get('timestamp')
            },
            'selection_context': {
                'selected_at_step': len(self.operations),  # 在第几步操作后选择的
                'page_url': self.page.url if hasattr(self, 'page') and self.page else 'unknown'
            }
        }

