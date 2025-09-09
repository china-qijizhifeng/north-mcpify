import asyncio
from typing import Dict, List, Any
from src.utils.playwright_provider import get_playwright_instance, finalize_recording

async def arxiv_search_papers(topic: str, from_year: str, to_year: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    搜索arXiv上关于特定话题在特定时间范围内的论文
    
    Args:
        topic (str): 搜索的话题/关键词
        from_year (str): 开始年份 (YYYY格式)
        to_year (str): 结束年份 (YYYY格式)
        max_results (int): 最多返回的结果数量，默认10
    
    Returns:
        List[Dict[str, Any]]: 包含论文标题、链接和摘要的字典列表
    """
    browser, context, page = await get_playwright_instance(
        enable_recording=True,
        session_path="./test_session/session_20250909_150856",
        session_name="session_20250909_150856", 
        headless=False,
        viewport={"width": 1280, "height": 720}
    )
    
    try:
        # 1. 导航到arXiv首页
        print("Navigating to arXiv...")
        await page.goto("https://arxiv.org/", timeout=60000)
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        print(f"Successfully loaded: {page.url}")
        
        # 2. 点击Advanced Search链接
        print("Looking for Advanced Search link...")
        # 尝试多种方式找到Advanced Search链接
        advanced_search_selectors = [
            'a[href*="advanced"]',
            'a:has-text("Advanced Search")',
            'a:text("Advanced Search")'
        ]
        
        clicked = False
        for selector in advanced_search_selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                await page.click(selector)
                clicked = True
                print(f"Successfully clicked Advanced Search with selector: {selector}")
                break
            except Exception as e:
                print(f"Failed with selector {selector}: {e}")
                continue
        
        if not clicked:
            print("Failed to find Advanced Search link, navigating directly")
            await page.goto("https://arxiv.org/search/advanced", timeout=60000)
            
        # 等待页面加载，但设置较短的超时时间
        try:
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
        except:
            print("Load state timeout, but continuing...")
        print(f"Advanced search page loaded: {page.url}")
        
        # 3. 在搜索框中输入话题
        print(f"Entering search topic: {topic}")
        # 给页面一些额外的时间来加载元素
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('#terms-0-term', timeout=15000)
        await page.click('#terms-0-term')
        await page.fill('#terms-0-term', topic)
        
        # 4. 设置开始日期
        print(f"Setting from date: {from_year}")
        await page.wait_for_selector('#date-from_date', timeout=10000)
        await page.click('#date-from_date')
        await page.fill('#date-from_date', from_year)
        
        # 5. 设置结束日期
        print(f"Setting to date: {to_year}")
        await page.wait_for_selector('#date-to_date', timeout=10000) 
        await page.click('#date-to_date')
        await page.fill('#date-to_date', to_year)
        
        # 6. 确保显示摘要的选项被选中
        print("Checking abstracts display option...")
        try:
            abstracts_radio = page.locator('input[name="abstracts"][value="show"]')
            if await abstracts_radio.count() > 0:
                is_checked = await abstracts_radio.is_checked()
                if not is_checked:
                    await abstracts_radio.check()
                    print("Abstracts display option checked")
        except Exception as e:
            print(f"Warning: Could not set abstracts option: {e}")
        
        # 7. 点击搜索按钮
        print("Clicking search button...")
        await page.wait_for_selector('.button.is-link.is-medium', timeout=10000)
        await page.click('.button.is-link.is-medium')
        await page.wait_for_load_state('domcontentloaded', timeout=30000)
        print(f"Search results loaded: {page.url}")
        
        # 8. 等待搜索结果加载
        print("Waiting for search results...")
        await page.wait_for_timeout(3000)  # Give extra time for dynamic content
        
        # 尝试不同的选择器来找到结果
        results_selectors = [
            'ol.breathe-horizontal > li',
            '.arxiv-result',
            'li[class*="arxiv"]',
            'article',
            '.result-meta',
            '#main-container ol li'
        ]
        
        paper_elements = []
        for selector in results_selectors:
            try:
                elements = await page.locator(selector).all()
                if elements:
                    print(f"Found {len(elements)} results using selector: {selector}")
                    paper_elements = elements
                    break
            except Exception as e:
                print(f"Selector {selector} failed: {e}")
                continue
        
        if not paper_elements:
            print("No paper elements found, trying to debug page structure...")
            # 尝试获取页面内容进行调试
            page_content = await page.content()
            print("Page title:", await page.title())
            print("Current URL:", page.url)
            
            # 检查是否有搜索结果
            main_content = await page.locator('#main-container').text_content()
            if main_content:
                print("Main content preview:", main_content[:500])
            
            return []
        
        # 9. 提取论文信息
        print(f"Extracting paper information from {len(paper_elements)} elements...")
        papers = []
        
        # 限制结果数量
        for i, paper_element in enumerate(paper_elements[:max_results]):
            try:
                print(f"Processing paper {i+1}...")
                
                # 提取标题 - 基于实际HTML结构
                title = ""
                try:
                    title_elem = await paper_element.locator('p.title.is-5.mathjax').first
                    if title_elem:
                        title_text = await title_elem.text_content()
                        if title_text and title_text.strip():
                            title = title_text.strip()
                            print(f"Found title: {title}")
                except Exception as e:
                    print(f"Title extraction failed: {e}")
                
                # 提取arXiv链接 - 从list-title中获取
                link = ""
                try:
                    link_elem = await paper_element.locator('p.list-title a[href*="/abs/"]').first
                    if link_elem:
                        href = await link_elem.get_attribute('href')
                        if href:
                            link = href if href.startswith('http') else f"https://arxiv.org{href}"
                            print(f"Found link: {link}")
                except Exception as e:
                    print(f"Link extraction failed: {e}")
                
                # 提取摘要
                abstract = ""
                abstract_selectors = [
                    '.abstract-full',
                    'span.abstract-full', 
                    '.abstract',
                    'span.abstract',
                    'p.abstract'
                ]
                
                for abs_sel in abstract_selectors:
                    try:
                        abstract_elem = await paper_element.locator(abs_sel).first
                        if abstract_elem:
                            abstract_text = await abstract_elem.text_content()
                            if abstract_text and abstract_text.strip():
                                abstract = abstract_text.replace('Abstract:', '').strip()
                                print(f"Found abstract with {abs_sel}: {abstract[:100]}...")
                                break
                    except:
                        continue
                
                if title or link:  # 至少要有标题或链接
                    papers.append({
                        'title': title,
                        'link': link, 
                        'abstract': abstract
                    })
                    print(f"Successfully extracted paper {i+1}")
                else:
                    print(f"Could not extract meaningful data from paper {i+1}")
                
            except Exception as e:
                print(f"Error extracting paper {i+1}: {e}")
                continue
        
        print(f"Successfully extracted {len(papers)} papers")
        return papers
        
    except Exception as e:
        print(f"Error during search: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    finally:
        # 结束录制
        try:
            recording_info = await finalize_recording("session_20250909_150856")
            print(f"Recording saved: {recording_info}")
        except Exception as e:
            print(f"Error finalizing recording: {e}")

# 测试函数
async def main():
    papers = await arxiv_search_papers("Large", "2025", "2025", 10)
    
    print(f"\nFound {len(papers)} papers:")
    for i, paper in enumerate(papers, 1):
        print(f"\n{i}. Title: {paper['title']}")
        print(f"   Link: {paper['link']}")
        if paper['abstract']:
            abstract_preview = paper['abstract'][:200] + "..." if len(paper['abstract']) > 200 else paper['abstract']
            print(f"   Abstract: {abstract_preview}")
        else:
            print(f"   Abstract: [No abstract found]")

if __name__ == "__main__":
    asyncio.run(main())