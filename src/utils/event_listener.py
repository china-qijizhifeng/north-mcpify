"""
事件监听器
捕获用户在页面上的交互事件
"""

import asyncio
from typing import Callable, Optional, Dict
from playwright.async_api import Page
from rich.console import Console

console = Console()

class EventListener:
    """网页事件监听器"""
    
    def __init__(self):
        self.listeners_setup = False
    
    async def setup_listeners(
        self, 
        page: Page,
        on_click: Optional[Callable] = None,
        on_input: Optional[Callable] = None,
        on_navigation: Optional[Callable] = None,
        on_element_selection: Optional[Callable] = None,
        on_element_selection_mode_start: Optional[Callable] = None,
        recorder = None  # 添加recorder参数用于移除遮罩
    ):
        """设置事件监听器"""
        if self.listeners_setup:
            return
        
        # 检查page对象
        if not page:
            raise ValueError("Page对象为None")
        
        try:
            console.print("🔧 验证Context级别的JavaScript事件监听器...")
            
            # 由于JavaScript已在context级别注入，这里只需要验证
            console.print("📋 JavaScript事件监听器已在Context级别注入")

            # 暴露一个立即事件传输函数，确保导航前事件不丢失
            async def __automation_emit(event: Dict):  # noqa: N802
                try:
                    # 为事件附带来源页面，便于后续在正确的Page上截图
                    try:
                        if isinstance(event, dict):
                            event['__page'] = page
                            try:
                                event.setdefault('page_url', getattr(page, 'url', None))
                            except Exception:
                                pass
                        else:
                            event = {'raw': event, '__page': page}
                    except Exception:
                        pass

                    event_type = (event or {}).get('type')
                    if event_type == 'click' and on_click:
                        asyncio.create_task(on_click(event))
                    elif event_type == 'input' and on_input:
                        asyncio.create_task(on_input(event))
                    elif event_type == 'navigation_intercepted' and on_navigation:
                        asyncio.create_task(on_navigation(event))
                    elif event_type == 'element_selected' and on_element_selection:
                        asyncio.create_task(on_element_selection(event))
                    elif event_type == 'element_selection_mode_start' and on_element_selection_mode_start:
                        asyncio.create_task(on_element_selection_mode_start(event))
                except Exception as emit_err:
                    console.print(f"⚠️  __automationEmit处理失败: {emit_err}")

            try:
                await page.expose_function("__automationEmit", __automation_emit)
                console.print("✅ 已暴露快速事件通道: __automationEmit")
            except Exception as expose_err:
                console.print(f"⚠️  暴露__automationEmit失败: {expose_err}")
            
        except Exception as e:
            console.print(f"❌ 事件监听器验证失败: {e}")
            raise
        
        # 启动事件检查循环 - 修复版本
        async def check_events_loop():
            console.print("🔄 事件检查循环开始运行...")
            loop_count = 0
            consecutive_errors = 0
            
            # 等待页面和JavaScript准备就绪
            await asyncio.sleep(2)
            console.print("⏱️  等待页面和JavaScript初始化完成...")
            
            # 等待JavaScript初始化完成或强制初始化
            initialization_attempts = 0
            max_attempts = 10
            
            while initialization_attempts < max_attempts:
                try:
                    js_check = await page.evaluate('typeof window.webAutomationEvents !== "undefined"')
                    if js_check:
                        console.print("✅ JavaScript事件监听器已初始化")
                        break
                    else:
                        initialization_attempts += 1
                        console.print(f"⏳ 等待JavaScript初始化... ({initialization_attempts}/{max_attempts})")
                        
                        # 如果等待时间过长，尝试强制初始化
                        if initialization_attempts >= 5:
                            console.print("🔄 尝试在事件循环中强制初始化JavaScript...")
                            try:
                                await page.evaluate("""
                                    () => {
                                        if (!window.webAutomationEvents) {
                                            window.webAutomationEvents = [];
                                            window.generateSelector = function(element) {
                                                if (!element) return 'unknown';
                                                if (element.id) return '#' + element.id;
                                                if (element.className) {
                                                    const classes = element.className.split(' ').filter(c => c.trim());
                                                    if (classes.length > 0) return '.' + classes.join('.');
                                                }
                                                return element.tagName.toLowerCase();
                                            };
                                            window.generateRobustSelector = function(element) {
                                                try {
                                                    if (!element) return 'unknown';
                                                    if (element.id) return '#' + element.id;
                                                    const parts = [];
                                                    let el = element;
                                                    while (el && el.nodeType === 1 && parts.length < 6) {
                                                        let part = el.tagName.toLowerCase();
                                                        if (el.id) { part = part + '#' + el.id; parts.unshift(part); break; }
                                                        const className = (el.className || '').trim();
                                                        if (className && typeof className === 'string') {
                                                            const firstClass = className.split(' ').filter(Boolean)[0];
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
                                            };
                                            // 简单的XPath生成
                                            window.generateXPath = function(element) {
                                                try {
                                                    if (!element) return '';
                                                    if (element.nodeType !== 1) element = element.parentElement;
                                                    const maxDepth = 20; const segments = []; let el = element; let depth = 0;
                                                    while (el && el.nodeType === 1 && depth < maxDepth) {
                                                        let index = 1; let sib = el;
                                                        while ((sib = sib.previousElementSibling)) { if (sib.tagName === el.tagName) index++; }
                                                        segments.unshift(el.tagName.toLowerCase() + '[' + index + ']');
                                                        el = el.parentElement; depth++;
                                                    }
                                                    return '//' + segments.join('/');
                                                } catch (e) { return ''; }
                                            };
                                            // frame trace 生成（从顶层到当前frame）
                                            window.generateFrameTrace = function() {
                                                try {
                                                    function getFrameIndex(win) {
                                                        try {
                                                            if (!win.parent || win.parent === win) return null;
                                                            const frames = win.parent.frames;
                                                            for (let i = 0; i < frames.length; i++) { try { if (frames[i] === win) return i; } catch(_){} }
                                                            return null;
                                                        } catch (_) { return null; }
                                                    }
                                                    function buildXPathInParent(el) {
                                                        try {
                                                            if (!el) return null;
                                                            const segs = []; let cur = el; let depth = 0;
                                                            while (cur && cur.nodeType === 1 && depth < 20) {
                                                                let ix = 1, sib = cur;
                                                                while ((sib = sib.previousElementSibling)) { if (sib.tagName === cur.tagName) ix++; }
                                                                segs.unshift(cur.tagName.toLowerCase() + '[' + ix + ']');
                                                                cur = cur.parentElement; depth++;
                                                            }
                                                            return '//' + segs.join('/');
                                                        } catch (_) { return null; }
                                                    }
                                                    function getFrameElementInfo(win) {
                                                        const info = { index: getFrameIndex(win), name: null, selector: null, xpath_in_parent: null, tag: 'iframe', frame_url: null };
                                                        try { info.name = win.name || null; } catch(_){}
                                                        try { info.frame_url = win.location && win.location.href || null; } catch(_) { info.frame_url = null; }
                                                        try {
                                                            const fe = win.frameElement;
                                                            if (fe) {
                                                                const tag = (fe.tagName || '').toLowerCase();
                                                                info.tag = tag || 'iframe';
                                                                if (fe.id) info.selector = '#' + fe.id; else if (fe.className && typeof fe.className === 'string') {
                                                                    const cls = fe.className.trim().split(' ').filter(Boolean)[0];
                                                                    info.selector = cls ? tag + '.' + cls : tag;
                                                                } else { info.selector = tag; }
                                                                info.xpath_in_parent = buildXPathInParent(fe);
                                                            }
                                                        } catch(_){}
                                                        return info;
                                                    }
                                                    const chain = [];
                                                    try { let w = window; while (w !== w.top) { chain.unshift(getFrameElementInfo(w)); w = w.parent; } } catch(_){ }
                                                    let curUrl = null; try { curUrl = location.href; } catch(_){}
                                                    return { chain: chain, depth: chain.length, current_frame_url: curUrl };
                                                } catch(_) { return { chain: [], depth: 0, current_frame_url: null }; }
                                            };
                                            
                                            // 在window捕获阶段优先监听点击，避免被拦截
                                            window.addEventListener('click', (event) => {
                                                try { if (event.__automationCapturedByWindow) return; event.__automationCapturedByWindow = true; } catch (e) {}
                                                try {
                                                    if (window.elementSelectionMode) {
                                                        return;
                                                    }
                                                } catch (e) {}
                                                try {
                                                    const eventData = {
                                                        type: 'click',
                                                        selector: window.generateSelector(event.target),
                                                        robust_selector: window.generateRobustSelector(event.target),
                                                        text_content: event.target.textContent?.trim() || '',
                                                        timestamp: Date.now(),
                                                        x: event.clientX,
                                                        y: event.clientY,
                                                        frame_url: (function(){ try { return location.href; } catch(_) { return null; } })(),
                                                        frame_trace: (typeof window.generateFrameTrace === 'function') ? window.generateFrameTrace() : null,
                                                        xpath: (typeof window.generateXPath === 'function') ? window.generateXPath(event.target) : ''
                                                    };
                                                    try {
                                                        const el = event.target;
                                                        const rect = el.getBoundingClientRect();
                                                        const attrs = {};
                                                        for (const a of Array.from(el.attributes || [])) { attrs[a.name] = a.value; }
                                                        const parent = el.parentElement;
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
                                                            selector: eventData.selector,
                                                            robust_selector: eventData.robust_selector,
                                                            element: {
                                                                tagName: el.tagName,
                                                                id: el.id,
                                                                className: el.className,
                                                                textContent: (el.textContent || '').trim(),
                                                                innerHTML: el.innerHTML,
                                                                outerHTML: el.outerHTML,
                                                                attributes: attrs,
                                                                boundingRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left },
                                                                isVisible: el.offsetParent !== null,
                                                                computedStyle: ''
                                                            },
                                                            parent: parentSummary,
                                                            page_title: document.title,
                                                            page_url: location.href,
                                                            timestamp: Date.now()
                                                        };
                                                    } catch (e) {}
                                                    if (typeof window.__automationEmit === 'function') {
                                                        try { eventData.__delivered = true; window.__automationEmit(eventData); } catch (e) {}
                                                    }
                                                    window.webAutomationEvents.push(eventData);
                                                    console.log('[WebAutomation] 强制初始化-WindowCapture-点击事件:', eventData);
                                                } catch (e) {}
                                            }, true);

                                            // 冒泡阶段监听：若window捕获已处理则跳过
                                            document.addEventListener('click', (event) => {
                                                try { if (event.__automationCapturedByWindow) return; } catch (e) {}
                                                try {
                                                    if (window.elementSelectionMode) {
                                                        return;
                                                    }
                                                } catch (e) {}
                                                try {
                                                    const eventData = {
                                                        type: 'click',
                                                        selector: window.generateSelector(event.target),
                                                        robust_selector: window.generateRobustSelector(event.target),
                                                        text_content: event.target.textContent?.trim() || '',
                                                        timestamp: Date.now(),
                                                        x: event.clientX,
                                                        y: event.clientY,
                                                        frame_url: (function(){ try { return location.href; } catch(_) { return null; } })(),
                                                        frame_trace: (typeof window.generateFrameTrace === 'function') ? window.generateFrameTrace() : null,
                                                        xpath: (typeof window.generateXPath === 'function') ? window.generateXPath(event.target) : ''
                                                    };
                                                    if (typeof window.__automationEmit === 'function') {
                                                        try { eventData.__delivered = true; window.__automationEmit(eventData); } catch (e) {}
                                                    }
                                                    window.webAutomationEvents.push(eventData);
                                                    console.log('[WebAutomation] 强制初始化-DocumentBubble-点击事件:', eventData);
                                                } catch (e) {}
                                            }, true);
                                            
                                            document.addEventListener('input', (event) => {
                                                try {
                                                    const eventData = {
                                                        type: 'input',
                                                        selector: window.generateSelector(event.target),
                                                        value: event.target.value || '',
                                                        timestamp: Date.now(),
                                                        frame_url: (function(){ try { return location.href; } catch(_) { return null; } })(),
                                                        frame_trace: (typeof window.generateFrameTrace === 'function') ? window.generateFrameTrace() : null,
                                                        xpath: (typeof window.generateXPath === 'function') ? window.generateXPath(event.target) : ''
                                                    };
                                                    if (typeof window.__automationEmit === 'function') {
                                                        try { eventData.__delivered = true; window.__automationEmit(eventData); } catch (e) {}
                                                    }
                                                    window.webAutomationEvents.push(eventData);
                                                    console.log('[WebAutomation] 强制初始化-输入事件:', eventData);
                                                } catch (e) {}
                                            }, true);
                                            
                                            console.log('[WebAutomation] 强制初始化完成');
                                        }
                                    }
                                """)
                            except Exception as e:
                                console.print(f"⚠️  强制初始化失败: {e}")
                        
                        await asyncio.sleep(0.5)
                except Exception:
                    initialization_attempts += 1
                    await asyncio.sleep(0.5)
            
            if initialization_attempts >= max_attempts:
                console.print("⚠️  JavaScript初始化超时，但事件循环将继续运行")
            
            while self.listeners_setup:
                try:
                    loop_count += 1
                    consecutive_errors = 0  # 重置错误计数
                    
                    if not page:
                        console.print("⚠️  页面对象不存在，退出事件循环")
                        break
                    
                    # 检查页面是否还活着
                    try:
                        page_url = page.url
                        if not page_url or page_url == "about:blank":
                            console.print("⚠️  页面已关闭或导航到about:blank，退出循环")
                            break
                    except Exception:
                        console.print("⚠️  无法获取页面URL，页面可能已关闭")
                        break
                        
                    # 获取并清空事件队列
                    try:
                        events = await page.evaluate('window.webAutomationEvents ? window.webAutomationEvents.splice(0) : []')
                    except Exception as e:
                        console.print(f"⚠️  获取事件队列失败: {e}")
                        events = []
                    
                    if events:
                        console.print(f"🎯 检测到 {len(events)} 个事件: {[e.get('type', 'unknown') for e in events]}")
                    elif loop_count % 10 == 0:  # 每5秒打印一次状态
                        # console.print(f"🔍 事件循环运行中... (第{loop_count}次检查)")
                        
                        # 定期检查JavaScript状态
                        try:
                            js_check = await page.evaluate('window.webAutomationEvents ? window.webAutomationEvents.length : -1')
                            if js_check != 0:
                                console.print(f"📊 事件队列状态: {js_check} 个事件等待处理")
                        except Exception as e:
                            console.print(f"⚠️  JavaScript状态检查失败: {e}")
                    
                    for event in events:
                        try:
                            # 同步补充来源页面信息，避免在其他页面/弹窗时回退到初始页面
                            try:
                                if isinstance(event, dict):
                                    event['__page'] = page
                                    try:
                                        event.setdefault('page_url', getattr(page, 'url', None))
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            # 跳过已通过快速通道上报的事件，避免重复
                            if isinstance(event, dict) and event.get('__delivered'):
                                continue
                            console.print(f"📝 处理事件: {event.get('type', 'unknown')} - {event.get('selector', 'N/A')}")
                            if event.get('type') == 'click' and on_click:
                                await on_click(event)
                            elif event.get('type') == 'input' and on_input:
                                await on_input(event)
                            elif event.get('type') == 'navigation_intercepted' and on_navigation:
                                console.print(f"🚫 检测到导航拦截事件，优先处理待处理操作")
                                await on_navigation(event)
                            elif event.get('type') == 'element_selected' and on_element_selection:
                                await on_element_selection(event)
                            elif event.get('type') == 'element_selection_mode_start' and on_element_selection_mode_start:
                                await on_element_selection_mode_start(event)
                        except Exception as e:
                            console.print(f"⚠️  处理单个事件失败: {e}")
                            console.print(f"⚠️  事件数据: {event}")
                    
                    await asyncio.sleep(0.5)  # 500ms检查间隔
                    
                except Exception as e:
                    consecutive_errors += 1
                    console.print(f"⚠️  事件循环异常: {e} (连续错误 {consecutive_errors} 次)")
                    console.print(f"⚠️  异常类型: {type(e).__name__}")
                    
                    # 连续错误太多次才退出，避免偶发错误导致循环退出
                    if consecutive_errors >= 5:
                        console.print("❌ 连续错误过多，退出事件循环")
                        break
                    else:
                        console.print("🔄 继续尝试事件检查...")
                        await asyncio.sleep(1)  # 出错时等待更长时间
            
            console.print("🛑 事件检查循环已退出")
        
        # 在后台启动事件检查任务（先标记为已设置，避免循环立即退出）
        self.listeners_setup = True
        self.event_check_task = asyncio.create_task(check_events_loop())
        console.print("✅ 事件检查循环已启动")
        
        # 等待页面加载并验证Context级别的JavaScript
        try:
            # 等待DOM加载完成
            await page.wait_for_load_state('domcontentloaded', timeout=10000)
            console.print("✅ 页面DOM加载完成")
            
            # 给页面一点时间执行context级别的init_script
            await asyncio.sleep(2)
            
            # 验证Context级别注入的JavaScript是否生效
            try:
                js_status = await page.evaluate("""
                    () => {
                        return {
                            eventsArrayExists: typeof window.webAutomationEvents !== 'undefined',
                            eventsCount: window.webAutomationEvents ? window.webAutomationEvents.length : 0,
                            location: window.location.href,
                            generateSelectorExists: typeof window.generateSelector === 'function',
                            readyState: document.readyState
                        };
                    }
                """)
                console.print(f"📊 Context JavaScript状态检查: {js_status}")
                
                if js_status.get('eventsArrayExists') and js_status.get('generateSelectorExists'):
                    console.print("✅ Context级别JavaScript注入成功！事件监听器已准备就绪")
                    # 通知recorder移除初始化遮罩
                    if recorder and hasattr(recorder, 'remove_initialization_overlay'):
                        try:
                            await recorder.remove_initialization_overlay()
                        except Exception as overlay_error:
                            console.print(f"⚠️ 移除遮罩失败: {overlay_error}")
                else:
                    console.print("⚠️  Context级别JavaScript可能未完全生效")
                    console.print("💡 事件监听器可能需要更多时间初始化")
                    # JavaScript未完全生效时也移除遮罩，避免用户被永久阻挡
                    if recorder and hasattr(recorder, 'remove_initialization_overlay'):
                        try:
                            await recorder.remove_initialization_overlay()
                            console.print("⚠️ 虽然JavaScript可能未完全就绪，但已移除遮罩避免阻挡用户")
                        except Exception as overlay_error:
                            console.print(f"⚠️ 移除遮罩失败: {overlay_error}")
                    
            except Exception as e:
                console.print(f"⚠️  JavaScript状态检查失败: {e}")
                console.print("💡 页面加载可能还未完成")
                # JavaScript状态检查失败时也移除遮罩，避免用户被永久阻挡
                if recorder and hasattr(recorder, 'remove_initialization_overlay'):
                    try:
                        await recorder.remove_initialization_overlay()
                        console.print("⚠️ JavaScript状态检查失败，但已移除遮罩避免阻挡用户")
                    except Exception as overlay_error:
                        console.print(f"⚠️ 移除遮罩失败: {overlay_error}")
                
        except Exception as e:
            console.print(f"⚠️  等待DOM加载超时: {e}")
            console.print("💡 页面加载较慢，继续启动事件循环")
        
        # 导航事件监听（暂时禁用以避免冲突）
        # if on_navigation:
        #     def handle_navigation_sync(frame):
        #         try:
        #             # 使用asyncio.create_task来异步调用
        #             import asyncio
        #             loop = asyncio.get_event_loop()
        #             loop.create_task(on_navigation({
        #                 'type': 'navigation',
        #                 'url': frame.url,
        #                 'timestamp': None
        #             }))
        #         except Exception:
        #             # 忽略所有导航事件错误，避免干扰录制
        #             pass
        #             
        #     page.on('framenavigated', handle_navigation_sync)
        
        # 页面关闭时清理事件监听器
        try:
            def cleanup_listeners():
                self.listeners_setup = False
                if hasattr(self, 'event_check_task') and self.event_check_task:
                    self.event_check_task.cancel()
                    
            page.on('close', cleanup_listeners)
            
        except Exception as e:
            console.print(f"⚠️  事件循环设置失败: {e}")
            raise
        
        # listeners_setup 已在启动循环前设置