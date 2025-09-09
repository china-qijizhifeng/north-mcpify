"""
会话管理器
负责会话的创建、存储、加载和管理
"""

import asyncio
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

from rich.console import Console
from src.execution.executor import FunctionExecutor
from src.utils.playwright_provider import PlaywrightProvider

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

class SessionManager:
    """会话管理器"""
    
    def __init__(self, sessions_dir: str = 'sessions'):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(exist_ok=True)
        self.playwright_provider = PlaywrightProvider()
    
    def load_session(self, session_id: str) -> Optional[Dict]:
        """加载会话数据"""
        session_path = self.sessions_dir / session_id
        if not session_path.exists():
            return None
        
        metadata_path = session_path / 'metadata.json'
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 加载操作数据
            operations_path = session_path / 'operations.json'
            if operations_path.exists():
                with open(operations_path, 'r', encoding='utf-8') as f:
                    operations = json.load(f)
                session_data['operations'] = operations
            
            # 加载AI分析结果
            analysis_path = session_path / 'ai_analysis.json'
            if analysis_path.exists():
                with open(analysis_path, 'r', encoding='utf-8') as f:
                    analysis = json.load(f)
                session_data['ai_analysis'] = analysis
            
            return session_data
            
        except Exception as e:
            console.print(f"❌ 加载会话失败: {e}", style="red")
            return None
    
    def save_analysis(self, session_id: str, analysis_result: Dict) -> bool:
        """保存AI分析结果"""
        session_path = self.sessions_dir / session_id
        if not session_path.exists():
            console.print(f"❌ 会话不存在: {session_id}", style="red")
            return False
        
        analysis_path = session_path / 'ai_analysis.json'
        
        try:
            # 添加时间戳
            analysis_result['analyzed'] = True
            analysis_result['analysis_timestamp'] = datetime.now().isoformat()
            
            with open(analysis_path, 'w', encoding='utf-8') as f:
                json.dump(analysis_result, f, ensure_ascii=False, indent=2)
            
            # 更新metadata中的分析状态
            metadata_path = session_path / 'metadata.json'
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                metadata['ai_analysis'] = analysis_result
                
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            console.print(f"❌ 保存分析结果失败: {e}", style="red")
            return False
    
    def list_sessions(self) -> List[Dict]:
        """列出所有会话"""
        sessions = []
        
        for session_dir in self.sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            
            metadata_path = session_dir / 'metadata.json'
            if not metadata_path.exists():
                continue
            
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # 确定会话状态
                status = self._determine_session_status(session_dir, metadata)
                
                sessions.append({
                    'id': session_dir.name,
                    'name': metadata.get('metadata', {}).get('name', 'Unknown'),
                    'url': metadata.get('metadata', {}).get('url', ''),
                    'created_at': metadata.get('timestamp', ''),
                    'status': status,
                    'operations_count': len(metadata.get('operations', [])),
                    'analyzed': metadata.get('ai_analysis', {}).get('analyzed', False)
                })
                
            except Exception as e:
                console.print(f"⚠️  读取会话 {session_dir.name} 失败: {e}", style="yellow")
        
        # 按创建时间倒序排列
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return sessions
    
    def _determine_session_status(self, session_dir: Path, metadata: Dict) -> str:
        """确定会话状态"""
        # 检查必要文件
        required_files = ['metadata.json', 'auth_state.json']
        missing_files = [f for f in required_files if not (session_dir / f).exists()]
        
        if missing_files:
            return 'incomplete'
        
        # 检查是否已分析
        if metadata.get('ai_analysis', {}).get('analyzed'):
            return 'analyzed'
        
        # 检查是否有操作记录
        if metadata.get('operations'):
            return 'recorded'
        
        return 'empty'
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session_path = self.sessions_dir / session_id
        if not session_path.exists():
            return False
        
        try:
            shutil.rmtree(session_path)
            return True
        except Exception as e:
            console.print(f"❌ 删除会话失败: {e}", style="red")
            return False
    
    def generate_function(self, session_id: str) -> str:
        """生成Python函数代码"""
        session_data = self.load_session(session_id)
        if not session_data:
            raise ValueError(f"会话不存在: {session_id}")
        
        analysis = session_data.get('ai_analysis', {})
        if not analysis.get('analyzed'):
            raise ValueError("会话尚未分析")
        
        operations = session_data.get('operations', [])
        suggested_params = analysis.get('suggested_parameters', [])
        function_name = session_data.get('metadata', {}).get('name', 'automation_function')
        
        # 清理函数名
        function_name = self._clean_function_name(function_name)
        
        # 生成函数签名
        params_str = self._generate_function_parameters(suggested_params)
        
        # 生成函数体
        function_body = self._generate_function_body(operations, suggested_params)
        
        # 生成完整函数代码
        function_code = f'''"""
自动生成的网页自动化函数
会话ID: {session_id}
生成时间: {datetime.now().isoformat()}
"""

import asyncio
from playwright.async_api import async_playwright
from typing import Optional, Dict, Any

async def {function_name}({params_str}) -> Dict[str, Any]:
    """
    {session_data.get('metadata', {}).get('name', '自动化函数')}
    
    参数:
{self._generate_param_docs(suggested_params)}
    
    返回:
        Dict[str, Any]: 执行结果
    """
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
{function_body}
            
            result = {{
                "success": True,
                "message": "自动化执行成功",
                "final_url": page.url,
                "title": await page.title()
            }}
            
        except Exception as e:
            result = {{
                "success": False,
                "error": str(e),
                "message": "自动化执行失败"
            }}
            
        finally:
            await browser.close()
        
        return result

# 同步包装函数
def {function_name}_sync({params_str}) -> Dict[str, Any]:
    """
    {function_name} 的同步版本
    """
    return asyncio.run({function_name}({self._generate_param_call(suggested_params)}))

if __name__ == "__main__":
    # 示例用法
    result = {function_name}_sync({self._generate_example_params(suggested_params)})
    print(result)
'''
        
        return function_code
    
    def _clean_function_name(self, name: str) -> str:
        """清理函数名"""
        import re
        # 移除非字母数字字符，转换为下划线
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name.strip())
        name = name.lower()
        
        # 确保以字母开头
        if name and not name[0].isalpha():
            name = 'automation_' + name
        
        return name or 'automation_function'
    
    def _generate_function_parameters(self, params: List[Dict]) -> str:
        """生成函数参数"""
        param_strs = []
        
        for param in params:
            param_name = param['name']
            param_type = param.get('type', 'str')
            default_value = param.get('default')
            required = param.get('required', True)
            
            if param_type == 'str':
                type_hint = 'str'
            elif param_type == 'int':
                type_hint = 'int'
            elif param_type == 'bool':
                type_hint = 'bool'
            else:
                type_hint = 'Any'
            
            if not required and default_value is not None:
                if param_type == 'str':
                    param_strs.append(f'{param_name}: {type_hint} = "{default_value}"')
                else:
                    param_strs.append(f'{param_name}: {type_hint} = {default_value}')
            elif not required:
                param_strs.append(f'{param_name}: Optional[{type_hint}] = None')
            else:
                param_strs.append(f'{param_name}: {type_hint}')
        
        return ', '.join(param_strs)
    
    def _generate_function_body(self, operations: List[Dict], params: List[Dict]) -> str:
        """生成函数体"""
        body_lines = []
        
        # 导航到起始页面
        if operations:
            first_op = operations[0]
            start_url = first_op.get('page_url', '')
            body_lines.append(f'            # 导航到起始页面')
            body_lines.append(f'            await page.goto("{start_url}")')
            body_lines.append('')
        
        # 生成操作代码
        for i, operation in enumerate(operations, 1):
            action = operation['action']
            selector = operation['selector']
            value = operation.get('value', '')
            
            body_lines.append(f'            # 步骤 {i}: {action}')
            
            if action == 'click':
                body_lines.append(f'            await page.click("{selector}")')
            elif action == 'input':
                # 检查是否需要参数化
                param_value = self._find_parameter_for_value(value, params)
                if param_value:
                    body_lines.append(f'            await page.fill("{selector}", {param_value})')
                else:
                    body_lines.append(f'            await page.fill("{selector}", "{value}")')
            elif action == 'navigation':
                body_lines.append(f'            await page.goto("{value}")')
            
            body_lines.append(f'            await page.wait_for_timeout(1000)')
            body_lines.append('')
        
        return '\n'.join(body_lines)
    
    def _find_parameter_for_value(self, value: str, params: List[Dict]) -> Optional[str]:
        """查找值对应的参数"""
        # 简单的参数匹配逻辑
        for param in params:
            param_name = param['name']
            if param_name.lower() in value.lower():
                return param_name
        return None
    
    def _generate_param_docs(self, params: List[Dict]) -> str:
        """生成参数文档"""
        docs = []
        for param in params:
            docs.append(f"        {param['name']} ({param.get('type', 'str')}): {param.get('description', '')}")
        return '\n'.join(docs) if docs else '        无参数'
    
    def _generate_param_call(self, params: List[Dict]) -> str:
        """生成参数调用"""
        return ', '.join([param['name'] for param in params])
    
    def _generate_example_params(self, params: List[Dict]) -> str:
        """生成示例参数"""
        examples = []
        for param in params:
            if param.get('type') == 'str':
                examples.append(f"{param['name']}=\"示例值\"")
            elif param.get('type') == 'int':
                examples.append(f"{param['name']}=123")
            elif param.get('type') == 'bool':
                examples.append(f"{param['name']}=True")
            else:
                examples.append(f"{param['name']}=\"示例值\"")
        return ', '.join(examples)
    
    # ======= 新增AI分析接口 =======
    
    async def trigger_ai_analysis(
        self,
        session_folder_path: str,
        task_description: str,
        output_format_requirements: str,
        save_function_path: str = None
    ) -> Dict[str, Any]:
        """
        触发AI分析的入口函数
        
        Args:
            session_folder_path: 录制会话文件夹路径
            task_description: 用户任务描述
            output_format_requirements: 输出格式需求
            save_function_path: 可选的函数保存路径
            
        Returns:
            Dict: {
                "success": bool,
                "function_code": str,  # 最终函数代码
                "saved_path": str or None,  # 如果保存了文件的路径
                "ai_iterations": int,  # AI迭代次数
                "execution_tests": list  # 执行测试结果列表
            }
        """
        console.print(f"🤖 开始AI分析: {Path(session_folder_path).name}")
        console.print(f"🎯 任务描述: {task_description}")
        console.print(f"📋 输出格式需求: {output_format_requirements}")
        
        try:
            # 调用用户实现的AI分析逻辑
            final_function_code = await self.call_user_ai_analysis(
                session_folder_path, 
                task_description, 
                output_format_requirements
            )
            
            # 可选保存到文件
            saved_path = None
            if save_function_path:
                Path(save_function_path).parent.mkdir(parents=True, exist_ok=True)
                Path(save_function_path).write_text(final_function_code, encoding='utf-8')
                saved_path = save_function_path
                console.print(f"💾 函数代码已保存到: {saved_path}")
            
            return {
                "success": True,
                "function_code": final_function_code,
                "saved_path": saved_path,
                "message": "AI分析完成"
            }
            
        except NotImplementedError:
            console.print("⚠️ 请实现 call_user_ai_analysis 方法", style="yellow")
            return {
                "success": False,
                "error": "AI分析方法尚未实现",
                "function_code": "",
                "saved_path": None
            }
        except Exception as e:
            console.print(f"❌ AI分析失败: {e}", style="red")
            return {
                "success": False,
                "error": str(e),
                "function_code": "",
                "saved_path": None
            }

    
    def _load_session_from_folder(self, session_folder_path: str) -> Dict[str, Any]:
        """
        从文件夹加载会话数据的辅助方法
        
        Args:
            session_folder_path: 会话文件夹路径
            
        Returns:
            Dict: 完整的会话数据
        """
        session_path = Path(session_folder_path)
        if not session_path.exists():
            raise ValueError(f"会话文件夹不存在: {session_folder_path}")
        
        # 加载元数据
        metadata_path = session_path / 'metadata.json'
        if not metadata_path.exists():
            raise ValueError(f"元数据文件不存在: {metadata_path}")
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 加载操作数据
            operations_path = session_path / 'operations.json'
            if operations_path.exists():
                with open(operations_path, 'r', encoding='utf-8') as f:
                    operations = json.load(f)
                session_data['operations'] = operations
            
            # 添加文件夹路径信息
            session_data['session_folder_path'] = str(session_path)
            
            return session_data
            
        except Exception as e:
            raise ValueError(f"加载会话数据失败: {e}")
    
    def get_executor(self) -> FunctionExecutor:
        """
        获取函数执行器实例
        
        这是一个便捷方法，用户可以在AI分析逻辑中使用
        """
        return FunctionExecutor()
    
    def get_playwright_provider(self) -> PlaywrightProvider:
        """
        获取Playwright提供器实例
        
        这是一个便捷方法，用户可以在AI分析逻辑中使用
        """
        return self.playwright_provider    

    async def launch_agent(self, prompt: str) -> list[Message]:
        history = []
        async for message in query(
            prompt=prompt,
            options=ClaudeCodeOptions(
                allowed_tools=[
                    "Agent",
                    "Bash",
                    "Edit",
                    "Glob",
                    "Grep",
                    "LS",
                    "MultiEdit",
                    "NotebookEdit",
                    "NotebookRead",
                    "Read",
                    "TodoRead",
                    "TodoWrite",
                    "WebFetch",
                    "WebSearch",
                    "Write",
                ],
                permission_mode="acceptEdits",
            ),
        ):
            log_message = ""
            if isinstance(message, UserMessage):
                log_message = f"[User] {message.content}"
            elif isinstance(message, AssistantMessage):
                log_message = f"[Assistant] {message.content}"
            elif isinstance(message, SystemMessage):
                log_message = f"[System] {message.subtype} {str(message.data)}"
            elif isinstance(message, ResultMessage):
                log_message = f"[Result] {message.subtype} {message.result}"
            else:
                log_message = f"[Unknown] {str(message)}"
            # print(log_message)
            history.append(message)
        return history

    async def call_user_ai_analysis(
        self,
        session_folder_path: str,
        task_description: str,
        output_format_requirements: str
    ) -> str:
        prompt = '''我刚刚完成了用户对于一系列浏览器操作的动作收集，他的存储路径是$session_path，现在我想把录制的步骤变成可复用的真正的Python代码。我给你提供的$session_path路径有所有相关的录制信息。
<录制信息目录结构概览>
```
/your/custom/session_path/
├── screenshots/                  # 截图文件夹（步骤可能有跳跃）
│   ├── step_1.png                  # 第1步操作截图
│   ├── step_3.png                  # 第3步操作截图
│   └── step_N.png                  # 第N步操作截图
├── html_snapshots/              # HTML快照文件夹
│   ├── 000_www_example_com_.html   # 第1个页面的HTML快照
│   ├── 001_www_example_com_s.html  # 第2个页面的HTML快照
│   └── metadata.json               # HTML快照元数据
├── operations.json               # 操作记录文件
├── metadata.json                # 会话元数据
├── auth_state.json              # 浏览器认证状态
└── selected_element_highlight.png              # 用户选择的期望返回的内容被包含的元素的截图
```
### screenshots 文件夹
作用: 保存每个自动化操作步骤的屏幕截图，步骤可能不连续（是因为输入的多个事件会被合并为一个事件）

**文件命名规则**
- step_1.png - 第1步操作的截图
- step_3.png - 第3步操作的截图  
- step_N.png - 第N步操作的截图

**特点**
- 高亮显示: 截图中会高亮显示被操作的元素
- PNG格式: 无损压缩，清晰度高
- 按步骤排序: 文件名按操作顺序递增
- 包含元素信息: 截图上会显示元素的标签名、属性等信息

**示例截图内容**
- 点击按钮时：按钮会被红色边框高亮
- 输入文本时：输入框会被高亮，并显示输入的内容
- 页面导航时：整个页面的截图

### html_snapshots 文件夹
作用: 保存页面的HTML结构快照，用于分析页面变化

**文件结构**
```
html_snapshots/
├── 000_www_example_com_.html       # 清理后的HTML内容
├── 001_www_example_com_s.html      # 清理后的HTML内容
└── metadata.json                   # 快照元数据信息
```

**HTML文件内容**
```
<!--
URL: https://www.example.com/
-->
<!DOCTYPE html>
<html>
<head>
    <title>页面标题</title>
</head>
<body>
    xxxxx
</body>
</html>
```
### metadata.json 结构
```
{
  "snapshots": [
    {
      "url": "https://www.example.com/",
      "filename": "000_www_example_com_.html",
      "timestamp": "2025-09-09T10:47:06.499942"
    }
  ],
  "total_snapshots": 1,
  "created_at": "2025-09-09T10:47:07.656039"
}
```

### operations.json 文件
作用: 记录所有自动化操作的详细信息

**文件结构**
```
[
  {
    "step_id": 1,
    "timestamp": "2025-09-09T10:47:05.823170",
    "action": "navigation",
    "selector": "page",
    "value": "https://www.baidu.com",
    "text_content": "",
    "screenshot": "screenshots/step_1.png",
    "dom_context": {
      "page_title": "百度一下，你就知道",
      "page_url": "https://www.baidu.com/",
      "viewport": {"width": 1280, "height": 720}
    }
  },
  {
    "step_id": 2,
    "timestamp": "2025-09-09T10:47:06.234567",
    "action": "click",
    "selector": "#kw",
    "value": "",
    "text_content": "",
    "screenshot": "screenshots/step_2.png",
    "dom_context": {
      "selector": "#kw",
      "element": {
        "tagName": "INPUT",
        "id": "kw",
        "className": "s_ipt",
        "textContent": "",
        "innerHTML": "",
        "outerHTML": "<input id=\"kw\" name=\"wd\" class=\"s_ipt\" value=\"\" maxlength=\"255\" autocomplete=\"off\" placeholder=\"许凯虞书欣陷多重舆论风波\" style=\"\">"
       }
     }
  }
]
```

**字段说明**
- step_id: 操作步骤编号（从1开始）
- timestamp: 操作执行的精确时间戳
- action: 操作类型（navigation、click、input、select等）
- selector: CSS选择器或特殊标识符
- value: 操作值（如输入的文本、导航的URL等）
- text_content: 元素的文本内容
- screenshot: 对应截图文件的相对路径
- dom_context: DOM上下文信息，包含页面和元素状态等

### metadata.json 文件
作用: 保存会话的基本信息和配置

**文件结构**
```
{
  "session_id": "interactive_test",
  "timestamp": "2025-09-09T10:47:01.116205",
  "metadata": {
    "name": "interactive_test",
    "url": "programmatic",
    "title": "百度一下，你就知道",
    "browser": "chromium",
    "viewport": {
      "width": 1280,
      "height": 720
    }
  },
  "return_reference_element": {
    "description": "用户选择的包含目标内容的元素区域",
    "selector": "#content_left",
    "screenshot": "selected_element_highlight.png",
    "element_details": {
      "tag_name": "div",
      "id": "content_left",
      "class_name": "element-hover-highlight",
      "text_preview": "你好 - 百度百科 快捷键说明 空格: 播放 / 暂停Esc: 退出全屏 ↑: 音量提高10% ↓: 音量降低10% →: 单次快进5秒 ←: 单次快退5秒按住此处可拖拽 不再出现 可在播放器设置中重新打开小窗播放\n            \n            \n                \n                \n                \n              ",
      "selection_timestamp": 1757313539909
    },
    "selection_context": {
      "selected_at_step": 2,
      "page_url": "https://www.baidu.com/s?ie=utf-8&f=8&rsv_bp=1&rsv_idx=1&tn=baidu&wd=%E4%BD%A0%E5%A5%BD&fenlei=256&rsv_pq=0xf326035c0346d817&rsv_t=746dj9hfuH3QZckY9%2Fy0Qawyjh4ByKw7ZCuiDzgctiIRjFzwszfoPWe7WaIJ&rqlang=en&rsv_dl=tb&rsv_enter=0&rsv_sug3=7&rsv_sug1=1&rsv_sug7=100&rsv_btype=i&prefixsug=%25E4%25BD%25A0%25E5%25A5%25BD&rsp=7&inputT=3213&rsv_sug4=5597"
    }
  },
  "statistics": {
    "total_operations": 4,
    "total_screenshots": 4,
    "session_duration_seconds": 12.5,
    "pages_visited": ["https://www.baidu.com/"]
  }
}
```
### auth_state.json 文件
作用: 保存浏览器的认证状态，包括cookies、localStorage等

</录制信息目录结构概览>

<用户的要求>
### 用户对任务的描述
$任务描述

### 用户对期望内容的描述
$返回内容描述
</用户的要求>

<你的任务>
你需要首先理解用户当前的操作逻辑，然后根据用户期望返回的内容和描述写一个函数，他会把用户期望可变的内容作为函数参数传入（例如搜索的内容，设置搜索的范围等）。然后在函数中实现用户的操作逻辑。你需要基于我封装后的playwright执行，因为我加了很多record的功能，这样你在执行后，可以拿到对应的截图等，然后根据截图可以看到是哪里没执行好。检查是否执行好的时候，可以结合你运行函数后得到的结果，和用户当时录制时候的selected_element_highlight.png对应来分析，同时结合用户对期望内容的描述。如果出现问题你需要结合中间截图反复迭代函数直至任务完全成功。你的执行是没有selected_element_highlight.png文件的，所以你需要对比你的**函数输出结果**与用户当时录制的截图，对于中间过程的debug，你可以借助保存的html文件和函数trace的log以及当时用户执行时候的截图与你现在的截图进行对比。如果是点击某个按钮对应会触发跳转的话，截图的点击真实场景可能无法被捕捉到。

你需要使用如下的模板来创建函数(请注意下述的session_path是你要保存的session_path，而不是之前用户录制的session_path，保存的session_path是用来调试你的函数的，他会帮你记录点击事件等的截图，还有你触发了哪些事件，方便你调试)
```python
from src.utils.playwright_provider import get_playwright_instance, finalize_recording

browser, context, page = await get_playwright_instance(
    enable_recording=True,
    session_path="$save_session_path",
    session_name="$save_session_name",
    headless=False,
    viewport={"width": 1280, "height": 720}
)

# 一些点击等事件操作 xxxxxx

# 结束录制 - 注意这里需要传入session_name
recording_info = await finalize_recording("$save_session_name")
```

请在$save_session_path下创建一个`.result`的文件，你需要非常诚实的汇报你的结果，如果最后失败了，`.result`请写入"FAILED"，如果成功了，`.result`请写入"SUCCESS"。同时，如果成功了，请在$save_session_path下创建一个`function.py`的文件，你需要把仅把最后的的函数代码写入这个文件中。
</你的任务>
'''
        session_name = session_folder_path.split('/')[-1]
        save_session_path = './test_session' + '/' + session_name
        prompt = prompt.replace('$session_path', session_folder_path)
        prompt = prompt.replace('$任务描述', task_description)
        prompt = prompt.replace('$返回内容描述', output_format_requirements)
        prompt = prompt.replace('$save_session_path', save_session_path)
        prompt = prompt.replace('$save_session_name', session_name)
        # print(prompt)
        
        # 最多尝试3次
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            console.print(f"🤖 第 {attempt} 次AI分析尝试...", style="blue")
            
            try:
                # 执行AI分析
                history = await self.launch_agent(prompt)
                
                # 检查执行结果
                result_file_path = Path(save_session_path) / '.result'
                function_file_path = Path(save_session_path) / 'function.py'
                
                # 等待结果文件生成（最多等待30秒）
                console.print("⏳ 等待AI分析完成...", style="yellow")
                await self._wait_for_result_file(result_file_path, timeout=30)
                
                if result_file_path.exists():
                    result_content = result_file_path.read_text(encoding='utf-8').strip()
                    
                    if result_content == "SUCCESS":
                        console.print(f"✅ 第 {attempt} 次尝试成功！", style="green")
                        
                        if function_file_path.exists():
                            function_code = function_file_path.read_text(encoding='utf-8')
                            console.print("📝 成功获取生成的函数代码", style="green")
                            return function_code
                        else:
                            console.print("⚠️ 缺少函数文件，尝试继续...", style="yellow")
                    
                    elif result_content == "FAILED":
                        console.print(f"❌ 第 {attempt} 次尝试失败", style="red")
                        if attempt < max_attempts:
                            console.print(f"🔄 准备第 {attempt + 1} 次重试...", style="yellow")
                            await asyncio.sleep(2)  # 短暂等待后重试
                        continue
                else:
                    console.print(f"⚠️ 第 {attempt} 次尝试无结果文件", style="yellow")
                    if attempt < max_attempts:
                        console.print(f"🔄 准备第 {attempt + 1} 次重试...", style="yellow")
                        await asyncio.sleep(2)
                    continue
                    
            except Exception as e:
                import traceback
                console.print(f"❌ 第 {attempt} 次尝试出现异常: {e}", style="red")
                console.print(f"❌ 第 {attempt} 次尝试出现异常: {traceback.format_exc()}", style="red")
                if attempt < max_attempts:
                    console.print(f"🔄 准备第 {attempt + 1} 次重试...", style="yellow")
                    await asyncio.sleep(2)
                continue
        
        # 所有尝试都失败了
        console.print("❌ 所有AI分析尝试均失败", style="red")
        
        # 返回一个基本的错误函数模板
        error_function = f'''
"""
AI分析失败，返回基本模板函数
会话: {session_folder_path}
任务描述: {task_description}
"""

async def failed_analysis_function():
    """AI分析失败的占位函数"""
    return {{
        "success": False,
        "error": "AI分析失败，请检查录制数据并重试",
        "session_path": "{session_folder_path}",
        "task_description": "{task_description}"
    }}

# 同步版本
def failed_analysis_function_sync():
    import asyncio
    return asyncio.run(failed_analysis_function())
'''
        return error_function
    
    async def _wait_for_result_file(self, result_file_path: Path, timeout: int = 30):
        """等待结果文件生成"""
        import asyncio
        
        for i in range(timeout):
            if result_file_path.exists():
                return
            await asyncio.sleep(1)
        
        # 超时后不抛出异常，让上级逻辑处理
