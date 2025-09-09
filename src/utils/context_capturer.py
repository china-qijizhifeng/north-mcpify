"""
上下文捕获器
捕获DOM元素上下文和页面状态
"""

from typing import Dict, Optional
from playwright.async_api import Page

class ContextCapturer:
    """页面上下文捕获器"""
    
    async def capture_element_context(self, page: Page, selector: str) -> Dict:
        """捕获元素的DOM上下文"""
        if not selector:
            return {}
        
        try:
            # 获取元素信息
            element_info = await page.evaluate(f"""
            (selector) => {{
                const element = document.querySelector(selector);
                if (!element) return null;
                
                return {{
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    textContent: element.textContent?.trim(),
                    innerHTML: element.innerHTML,
                    outerHTML: element.outerHTML,
                    attributes: Array.from(element.attributes).reduce((acc, attr) => {{
                        acc[attr.name] = attr.value;
                        return acc;
                    }}, {{}}),
                    boundingRect: element.getBoundingClientRect(),
                    isVisible: element.offsetParent !== null,
                    computedStyle: window.getComputedStyle(element).cssText
                }};
            }}
            """, selector)
            
            if not element_info:
                return {'error': 'Element not found', 'selector': selector}
            
            # 获取父元素上下文
            parent_context = await page.evaluate(f"""
            (selector) => {{
                const element = document.querySelector(selector);
                if (!element || !element.parentElement) return null;
                
                const parent = element.parentElement;
                return {{
                    tagName: parent.tagName,
                    id: parent.id,
                    className: parent.className,
                    children: Array.from(parent.children).map(child => {{
                        return {{
                            tagName: child.tagName,
                            id: child.id,
                            className: child.className,
                            textContent: child.textContent?.trim()
                        }};
                    }})
                }};
            }}
            """, selector)
            
            return {
                'selector': selector,
                'element': element_info,
                'parent': parent_context,
                'page_title': await page.title(),
                'page_url': page.url,
                'timestamp': None
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'selector': selector
            }
    
    async def capture_page_state(self, page: Page) -> Dict:
        """捕获页面状态"""
        try:
            page_state = await page.evaluate("""
            () => {{
                return {{
                    title: document.title,
                    url: window.location.href,
                    readyState: document.readyState,
                    forms: Array.from(document.forms).map(form => ({{
                        id: form.id,
                        name: form.name,
                        action: form.action,
                        method: form.method,
                        elements: Array.from(form.elements).map(el => ({{
                            name: el.name,
                            type: el.type,
                            value: el.value
                        }}))
                    }})),
                    links: Array.from(document.links).slice(0, 10).map(link => ({{
                        href: link.href,
                        text: link.textContent?.trim()
                    }})),
                    scripts: Array.from(document.scripts).length,
                    images: Array.from(document.images).length,
                    viewport: {{
                        width: window.innerWidth,
                        height: window.innerHeight
                    }}
                }};
            }}
            """)
            
            return page_state
            
        except Exception as e:
            return {'error': str(e)}