"""
测试用户的具体使用案例
"""

import asyncio
from src.utils.playwright_provider import get_playwright_instance, finalize_recording
from rich.console import Console

console = Console()

async def test_user_case():
    """测试用户的具体使用案例"""
    
    console.print("🧪 测试用户案例", style="bold blue")
    
    try:
        browser, context, page = await get_playwright_instance(
            enable_recording=True,
            session_path="/Users/kausal/north_mcpify/interactive_test",
            headless=False,  # 显示浏览器以便观察
            viewport={"width": 1280, "height": 720}
        )
        console.print("✅ 实例创建成功")
        
        # 执行操作
        await page.goto("https://www.baidu.com")
        await page.click("#kw")
        await page.fill("#kw", "用户测试")
        await page.click("#su")
        await page.wait_for_selector(".result", timeout=10000)
        
        # 结束录制 - 注意这里需要传入session_name
        # 由于没有指定session_name，可能需要使用默认值或路径名
        recording_info = await finalize_recording("interactive_test")
        await browser.close()
        
        console.print(f"✅ 录制完成: {recording_info}")
        
        # 检查文件
        from pathlib import Path
        test_path = Path("/Users/kausal/north_mcpify/interactive_test")
        if test_path.exists():
            console.print(f"✅ 路径存在: {test_path}")
            
            screenshots = list((test_path / 'screenshots').glob('*.png'))
            operations_file = test_path / 'operations.json'
            metadata_file = test_path / 'metadata.json'
            
            console.print(f"📸 截图数量: {len(screenshots)}")
            console.print(f"📋 operations.json存在: {operations_file.exists()}")
            console.print(f"📄 metadata.json存在: {metadata_file.exists()}")
            
            if operations_file.exists():
                import json
                with open(operations_file, 'r') as f:
                    operations = json.load(f)
                console.print(f"📋 操作记录数量: {len(operations)}")
            else:
                console.print("❌ operations.json不存在")
        else:
            console.print(f"❌ 路径不存在: {test_path}")
            
    except Exception as e:
        console.print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_user_case())