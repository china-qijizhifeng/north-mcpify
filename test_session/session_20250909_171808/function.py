import asyncio
import re
from typing import List, Dict, Any
from src.utils.playwright_provider import get_playwright_instance, finalize_recording

async def search_arxiv_papers(search_term: str, from_date: str, to_date: str, max_papers: int = 10) -> List[Dict[str, Any]]:
    """
    Search arXiv for papers on a specific topic within a date range.
    
    Args:
        search_term: The topic to search for
        from_date: Start date in YYYY format  
        to_date: End date in YYYY format
        max_papers: Maximum number of papers to return (default 10)
    
    Returns:
        List of dictionaries containing paper information (title, abstract, link)
    """
    
    browser, context, page = await get_playwright_instance(
        enable_recording=True,
        session_path="./test_session/session_20250909_150856",
        session_name="session_20250909_150856",
        headless=False,
        viewport={"width": 1280, "height": 720}
    )
    
    page.set_default_timeout(60000)  # Set default timeout to 60 seconds

    try:
        # Navigate to arXiv homepage
        await page.goto("https://arxiv.org/")
        await page.wait_for_load_state('networkidle')
        
        # Click on Advanced Search link
        await page.click('a[href="https://arxiv.org/search/advanced"]')
        await page.wait_for_load_state('networkidle')
        
        # Fill in search term
        await page.click("#terms-0-term")
        await page.fill("#terms-0-term", search_term)
        
        # Set date range - from date
        await page.click("#date-from_date")
        await page.fill("#date-from_date", from_date)
        
        # Set date range - to date
        await page.click("#date-to_date") 
        await page.fill("#date-to_date", to_date)
        
        # Click search button
        await page.click(".button.is-link.is-medium")
        await page.wait_for_load_state('networkidle')
        
        # Wait for paper results to load  
        try:
            await page.wait_for_selector("li.arxiv-result", timeout=30000)
        except Exception as e:
            print(f"Timeout waiting for results, but continuing to extract available data: {e}")
        
        # Extract paper information
        papers = []
        
        # Find all arxiv-result list items
        results = await page.query_selector_all("li.arxiv-result")
        
        for i, result in enumerate(results[:max_papers]):
            try:
                # Extract arXiv ID and link
                link_element = await result.query_selector("p.list-title a[href*='arxiv.org']")
                if link_element:
                    link = await link_element.get_attribute("href")
                    arxiv_id = await link_element.text_content()
                else:
                    continue
                
                # Extract title
                title_element = await result.query_selector("p.title")
                if title_element:
                    title = await title_element.text_content()
                    title = title.strip()
                else:
                    title = "No title found"
                
                # Extract abstract
                abstract_element = await result.query_selector("p.abstract .abstract-full")
                if not abstract_element:
                    abstract_element = await result.query_selector("p.abstract .abstract-short")
                
                if abstract_element:
                    abstract = await abstract_element.text_content()
                    abstract = abstract.strip()
                    # Remove "Abstract:" prefix if present
                    abstract = re.sub(r'^Abstract:\s*', '', abstract)
                else:
                    abstract = "No abstract found"
                
                papers.append({
                    "arxiv_id": arxiv_id.strip(),
                    "title": title,
                    "abstract": abstract,
                    "link": f"https://arxiv.org{link}" if not link.startswith("http") else link
                })
                
            except Exception as e:
                print(f"Error extracting paper {i}: {e}")
                continue
        
        return papers
        
    except Exception as e:
        print(f"Error during arXiv search: {e}")
        return []
    
    finally:
        # End recording
        recording_info = await finalize_recording("session_20250909_150856")
        print(f"Recording saved to: {recording_info}")