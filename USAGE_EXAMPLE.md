# 🎯 使用统一Playwright接口的AI函数示例

## 📋 用户实现AI分析的标准模式

在 `SessionManager.call_user_ai_analysis()` 方法中，用户可以这样生成和测试函数：

```python
async def call_user_ai_analysis(
    self,
    session_folder_path: str,
    task_description: str,
    output_format_requirements: str
) -> str:
    """用户的AI分析实现"""
    
    # 1. 加载session数据
    session_data = self._load_session_from_folder(session_folder_path)
    
    # 2. 基于任务描述和操作记录，AI生成函数代码
    operations = session_data.get('operations', [])
    task_def = session_data.get('task_definition', {})
    
    # 这里是你的AI逻辑，根据录制数据生成函数
    # 示例生成的函数：
    generated_function = f'''
from src.utils.playwright_provider import get_playwright_instance, finalize_recording

async def search_baidu(keyword: str) -> dict:
    """在百度搜索关键词并返回结果"""
    
    # 获取带录制功能的Playwright实例
    browser, context, page = await get_playwright_instance(
        enable_recording=True,
        session_name="baidu_search",
        headless=False  # 调试时可以看到浏览器
    )
    
    try:
        # 执行自动化操作
        await page.goto("https://www.baidu.com")
        await page.fill("#kw", keyword)
        await page.click("#su")
        await page.wait_for_selector(".result")
        
        # 提取搜索结果
        results = []
        result_elements = await page.query_selector_all(".result h3 a")
        for element in result_elements[:5]:  # 前5个结果
            title = await element.text_content()
            href = await element.get_attribute("href")
            results.append({{"title": title, "url": href}})
        
        # ✨ 完成录制并获取录制数据（自动停止录制！）
        recording_info = await finalize_recording(
            "baidu_search",
            "./test_recording"
        )
        
        return {{
            "success": True,
            "results": results,
            "recording_info": recording_info  # 包含录制数据
        }}
        
    finally:
        await browser.close()
        
    # 💡 注意：调用 finalize_recording() 后录制会自动停止
    # 无需手动按 Ctrl+C 或等待用户交互
'''
    
    # 3. 测试生成的函数
    executor = self.get_executor()
    
    for iteration in range(3):  # 最多3次迭代
        console.print(f"🔄 第{iteration+1}次测试...")
        
        test_result = await executor.execute_with_recording(
            function_code=generated_function,
            function_params={{"keyword": "Python教程"}},
            recording_output_dir=f"./ai_test/iteration_{iteration}",
            session_name=f"test_{iteration}"
        )
        
        if test_result["success"]:
            execution_result = test_result["execution_result"]
            
            # 检查是否符合要求
            if (isinstance(execution_result, dict) and 
                execution_result.get("success") and 
                len(execution_result.get("results", [])) > 0):
                
                console.print("✅ 函数测试成功，返回最终代码")
                return generated_function
            else:
                console.print("⚠️ 结果不符合要求，需要优化...")
                # 这里可以基于执行结果进行AI优化
        
        else:
            console.print("❌ 执行失败，需要修复代码...")
            # 基于错误信息修复代码
    
    # 返回最后一次迭代的结果
    return generated_function
```

## 🔧 关键优势

### 1. 用户代码简洁
```python
# 用户只需要调用统一接口
browser, context, page = await get_playwright_instance(enable_recording=True)

# 而不是自己管理复杂的录制逻辑
```

### 2. 录制数据完整与自动终止
```python
# 函数执行完成后，自动停止录制并获得完整的录制数据
recording_info = await finalize_recording("session_name")

# ✨ 新特性：程序化录制终止
# - 调用 finalize_recording() 会自动停止录制
# - 无需等待用户按 Ctrl+C 或关闭浏览器
# - AI函数执行完毕立即结束，提高效率

# 包含完整录制数据：
# - 截图路径
# - HTML快照
# - 操作记录
# - 录制会话路径
```

### 3. 灵活控制
```python
# 调试时开启录制和可视化
browser, context, page = await get_playwright_instance(
    enable_recording=True,
    headless=False,
    session_name="debug_session"
)

# 生产环境关闭录制
browser, context, page = await get_playwright_instance(
    enable_recording=False,
    headless=True
)
```

## 📊 数据流示例

1. **AI生成函数** → 使用 `get_playwright_instance(enable_recording=True)`
2. **执行操作** → 自动录制所有操作、截图、HTML
3. **调用 `finalize_recording()`** → 🚀 **程序化自动停止录制** + 获取录制数据
4. **返回结果** → 包含业务结果 + 录制信息
5. **FunctionExecutor** → 收集并分析执行结果
6. **AI分析** → 基于录制数据优化函数

### 🚀 程序化录制终止流程：
```
AI函数执行完毕 
    ↓
调用 finalize_recording()
    ↓  
设置 stop_recording_flag
    ↓
录制循环检测到停止信号
    ↓
立即停止录制，保存会话数据
    ↓
返回完整录制信息
```

## 🎯 对比功能

现在你可以轻松实现：

```python
# 原始录制的最终截图路径
original_screenshot = "sessions/original_session/screenshots/final.png"

# AI执行的最终截图路径  
ai_execution_result = await executor.execute_with_recording(function_code, params)
ai_screenshot = ai_execution_result["recording_data"]["final_screenshot"]

# 对比两张截图
if compare_screenshots(original_screenshot, ai_screenshot):
    print("✅ 执行结果与预期一致")
else:
    print("❌ 需要优化AI函数")
```

## 🎉 新增特性总结

### ✅ 程序化录制终止
- **自动停止**：调用 `finalize_recording()` 后录制自动停止
- **无需交互**：AI函数执行完毕立即结束，无需等待用户操作
- **高效迭代**：多次测试时每次都能快速完成录制

### ✅ 完整的生命周期管理
```python
# 1. 启动录制
browser, context, page = await get_playwright_instance(enable_recording=True)

# 2. 执行操作（自动录制）
await page.goto("https://example.com")
await page.click("#button")

# 3. 程序化停止录制
recording_info = await finalize_recording("session_name")

# 4. 录制立即结束，获得完整数据
```

### ✅ AI迭代优化流程
1. **生成函数** → 包含录制调用
2. **执行测试** → 自动录制 + 自动停止
3. **对比结果** → 截图、HTML、操作记录
4. **AI优化** → 基于录制数据改进函数
5. **重复迭代** → 直到达到预期效果

这个方案让你完全掌控AI分析和迭代的过程，实现了真正的自动化！