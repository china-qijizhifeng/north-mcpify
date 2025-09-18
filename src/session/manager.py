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
import subprocess
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
        return await self.launch_codex_agent(prompt)


    async def launch_codex_agent(self, prompt: str) -> list[Message]:
        # 执行命令 codex exec --dangerously-bypass-approvals-and-sandbox  $prompt
        command = f"codex exec --dangerously-bypass-approvals-and-sandbox  {json.dumps(prompt, ensure_ascii=False)}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        print(result)
        return result.stdout


    async def launch_claude_agent(self, prompt: str) -> list[Message]:
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
        # 所有任务都使用多场景分析逻辑
        return await self._analyze_multi_scenario_task(
            session_folder_path, task_description, output_format_requirements
        )
    
    async def _analyze_multi_scenario_task(
        self,
        session_folder_path: str,
        task_description: str,
        output_format_requirements: str
    ) -> str:
        """分析多场景任务"""
        # 加载任务数据
        task_data = self._load_multi_scenario_data(session_folder_path)
        
        # 构建多场景提示词
        prompt = self._build_multi_scenario_prompt(
            session_folder_path, task_data, task_description, output_format_requirements
        )
        
        # 执行AI分析
        return await self._execute_ai_analysis(prompt, session_folder_path)
    
    def _load_multi_scenario_data(self, session_folder_path: str) -> Dict:
        """加载任务数据，兼容单场景和多场景格式"""
        session_path = Path(session_folder_path)
        
        # 检查是否为多场景格式
        task_metadata_file = session_path / "task_metadata.json"
        is_multi_scenario = task_metadata_file.exists() or len(list(session_path.glob("recording_*"))) > 0
        
        if is_multi_scenario:
            # 多场景格式
            task_metadata = {}
            if task_metadata_file.exists():
                with open(task_metadata_file, 'r', encoding='utf-8') as f:
                    task_metadata = json.load(f)
            
            # 从task_metadata中获取final_description，如果没有则尝试从单独文件读取（向后兼容）
            final_description = task_metadata.get("final_description", {})
            if not final_description:
                final_description_file = session_path / "final_description.json"
                if final_description_file.exists():
                    with open(final_description_file, 'r', encoding='utf-8') as f:
                        final_description = json.load(f)
            
            # 加载所有录制场景数据
            recordings_data = []
            recording_dirs = sorted(session_path.glob("recording_*"))
            
            for recording_dir in recording_dirs:
                recording_data = {
                    "recording_id": recording_dir.name,
                    "path": str(recording_dir)
                }
                
                # 加载该录制的元数据
                metadata_file = recording_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        recording_data["metadata"] = json.load(f)
                
                # 加载操作数据
                operations_file = recording_dir / "operations.json"
                if operations_file.exists():
                    with open(operations_file, 'r', encoding='utf-8') as f:
                        recording_data["operations"] = json.load(f)
                
                recordings_data.append(recording_data)
            
            return {
                "task_metadata": task_metadata,
                "final_description": final_description,
                "recordings": recordings_data
            }
        
        else:
            # 单场景格式，转换为多场景格式
            metadata_file = session_path / "metadata.json"
            operations_file = session_path / "operations.json"
            
            # 构建兼容的任务元数据
            task_metadata = {
                "task_id": session_path.name,
                "task_description": "单场景任务",
                "recordings": [
                    {
                        "recording_id": "single_recording",
                        "scenario_description": "主要操作流程",
                        "completed_at": datetime.now().isoformat()
                    }
                ]
            }
            
            # 构建兼容的最终描述
            final_description = {
                "description": "基于单场景录制的自动化函数",
                "type": "dict",
                "scenarios_count": 1
            }
            
            # 构建兼容的录制数据
            recordings_data = [{
                "recording_id": "single_recording",
                "path": str(session_path)
            }]
            
            # 加载单场景的元数据和操作
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    recordings_data[0]["metadata"] = json.load(f)
            
            if operations_file.exists():
                with open(operations_file, 'r', encoding='utf-8') as f:
                    recordings_data[0]["operations"] = json.load(f)
            
            return {
                "task_metadata": task_metadata,
                "final_description": final_description,
                "recordings": recordings_data
            }
    
    def _build_multi_scenario_prompt(
        self, 
        session_folder_path: str, 
        task_data: Dict, 
        task_description: str, 
        output_format_requirements: str
    ) -> str:
        """构建多场景AI提示词"""
        recordings = task_data.get("recordings", [])
        task_metadata = task_data.get("task_metadata", {})
        
        # 构建场景描述
        scenarios_info = ""
        for i, recording in enumerate(recordings, 1):
            scenario_desc = "未描述"
            for rec_info in task_metadata.get("recordings", []):
                if rec_info.get("recording_id") == recording["recording_id"]:
                    scenario_desc = rec_info.get("scenario_description", "未描述")
                    break
            
            scenarios_info += f"场景{i}（{recording['recording_id']}）:\n{scenario_desc}\n\n"
        
        prompt = '''我刚刚完成了用户对于一系列浏览器操作的动作收集，他的存储路径是$session_path，其中可能包括多次用户的录制，每次录制都有用户的描述，他这次录制完成了什么样的任务，现在我想把录制的步骤变成可复用的真正的Python代码。我给你提供的$session_path路径有所有相关的录制信息。

<多次录制信息目录结构概览>
```
/your/custom/task_path/
├── task_metadata.json              # 任务总体信息、各场景描述和最终函数期望描述
├── recording_1/                    # 第一个场景录制
│   ├── screenshots/                  # 截图文件夹
│   │   ├── step_1.png               # 第1步操作截图
│   │   └── step_N.png               # 第N步操作截图
│   ├── html_snapshots/              # HTML快照文件夹
│   │   ├── 000_www_example_com_.html # 页面HTML快照
│   │   └── metadata.json            # HTML快照元数据
│   ├── operations.json              # 操作记录文件
│   ├── metadata.json               # 录制会话元数据
│   ├── auth_state.json             # 浏览器认证状态
│   └── selected_element_highlight.png # 用户选择的期望返回元素截图
├── recording_2/                    # 第二个场景录制
│   └── ...                         # 相同的文件结构
└── recording_N/                    # 第N个场景录制
    └── ...                         # 相同的文件结构
```

## 一些核心文件/文件夹说明

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

### record_x/operations.json 文件
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
        "innerHTML": "",
        "outerHTML": "<input id=\"kw\" name=\"wd\" class=\"s_ipt\" value=\"\" maxlength=\"255\" autocomplete=\"off\" placeholder=\"许凯虞书欣陷多重舆论风波\" style=\"\">"
       }
     }
  }
]
```

### recording_x/metadata.json 文件
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
      "text_preview": "xxx",
      "selection_timestamp": 1757313539909
    },
    "selection_context": {
      "selected_at_step": 2,
      "page_url": "xxx"
    }
  },
  "statistics": {
    "total_operations": 4,
    "total_screenshots": 4,
    "session_duration_seconds": 12.5,
    "pages_visited": ["xxx"]
  }
}
```

### recording_x/auth_state.json 文件
作用: 保存浏览器的认证状态，包括cookies、localStorage等

</多次录制信息目录结构概览>
'''+f'''
<用户的要求>
### 用户对任务的总体描述
{task_description}

### 各次录制的说明
{scenarios_info}

### 用户对期望内容的描述
{output_format_requirements}

注意：用户的期望内容描述也可以在task_metadata.json文件的final_description字段中找到更详细的信息。
</用户的要求>

<你的任务>
- 你需要首先理解用户当前的操作逻辑，然后根据用户期望返回的内容和描述写一个函数，函数会把用户期望可变的内容作为函数参数传入（例如搜索的内容，设置搜索的范围等）。然后在函数中实现用户的操作逻辑。
- 你需要基于我封装后的playwright执行，因为我加了很多record的功能，这样你在执行后，可以拿到输入/点击对应的截图等，然后根据截图可以看到是哪里没执行好。检查最终是否执行成功的时候，可以结合你运行函数后得到的结果，和用户当时录制时候的selected_element_highlight.png对应来分析，同时结合用户对期望内容的描述。如果出现问题你需要结合中间截图反复迭代函数直至任务完全成功。你的执行是没有selected_element_highlight.png文件的，所以你需要对比你的**函数输出结果**与用户当时录制的截图。你一定要确保你真正运行成功了每一次用户的录制的结果，而不是觉得可以工作就认为完成。
- 为了方便你理解，用户会点击一些可能需要注意的条件（这些并非真实需要的点击事件，但是用户为了方便你理解用户提出的需求，会点击，这些一般是纯文本内容，用来提示你可能需要关注这些地方）。
- 当结果不符合预期的时候，你可以借助保存的html文件和函数trace的log以及当时用户执行时候的截图与你现在执行后生成的截图进行对比。如果是点击某个按钮对应会触发跳转的话，截图的点击真实场景可能无法被捕捉到。请注意部分录制中可能包含iframe，他会在operations.json中xpath中记录。如果没能完成任务，结果不符合预期的原因很可能是**click或者input等事件的元素没选择对**（比如class相同的有多个元素等），这种情况下你可以仔细查看一下你的任务的截图，是否有符合在你预期的地方进行输入，grep等操作在网页中搜索一下对应class等等元素个数等，还有查查是否等待方式/时间是否不够等。
- 对于用class定位可能有重复的元素，请最好使用xpath的路径来点击，不要使用class来点击。
- 你需要使用如下的模板来创建函数(请注意下述的session_path是你要保存的session_path，而不是之前用户录制的session_path，保存的session_path是用来调试你的函数的，他会帮你记录点击事件等的截图，还有你触发了哪些事件，方便你调试)，同时你实现的代码需要确保用户所有的录制都能被成功的复现出来，注意等待的操作不止应该和时间有关系，还得和一些元素创建有关系。请确保你执行过最后创建的function.py能成功复现用户的所有操作，否则视任务为失败

```python
from src.utils.playwright_provider import get_playwright_instance, finalize_recording

browser, context, page = await get_playwright_instance(
    enable_recording=True,
    session_path="$save_session_path",
    session_name="$save_session_name",
    headless=False,
    viewport={{"width": 960, "height": 580}}
)

# 智能的多场景处理逻辑 xxxxxx
# 根据不同场景录制分析生成的分支处理代码

# 结束录制 - 注意这里需要传入session_name
recording_info = await finalize_recording("$save_session_name")
```

- 对于验证码的输入，你需要调用我提供的API接口，code字段就是返回的验证码，但是请注意验证码识别可能一次对不了，在你实现的代码中需要有多次识别的逻辑(至少5次），同时验证码图片你也可以考虑保存一份写到本地，看是否正确识别了验证码区域。
验证码解析函数：
```python
import requests


base64_img = "data:image/png;base64,xxxxxx"

token = "cSzHWVMeNPpaQ2G9x2gXRjoKwl_DeT4mGkkRcBcqSmQ"
url = "http://api.jfbym.com/api/YmServer/customApi"

payload = {{
    "image": base64_img,
    "token": token,
    "type": '10110',
}}

try:
    resp = requests.post(url, json=payload, timeout=30).json()
    code = resp['data']['data']
except requests.RequestException as e:
    code = "0000"
```

- 最后，请在$save_session_path下创建一个`.result`的文件，你需要非常诚实的汇报你的结果，如果最后失败了，`.result`请写入"FAILED"，如果成功了，`.result`请写入"SUCCESS"。不要轻易放弃，只要还有机会，如果请尽量多的尝试，不要急躁，不要有畏难情绪。同时，如果成功了，请在$save_session_path下创建一个`function.py`的文件，你需要把仅把最后的的一个函数代码写入这个文件中。在写代码过程中遇到问题可以去看看生成的截图等，辅助debug是不是元素定位有问题等。请一直执行，无需寻求用户的同意，直到完成整个任务，创建完成.result和function.py文件。function.py仅能包含一个函数，不能包含其他代码，调试的代码请写入其他代码文件中，在调试完成后再将最终的一个函数（包含函数的docstring）写入function.py文件中。
</你的任务>
'''
        return prompt
    
    async def _execute_ai_analysis(self, prompt: str, session_folder_path: str) -> str:
        """执行AI分析"""
        session_name = session_folder_path.split('/')[-1]
        save_session_path = './test_session' + '/' + session_name
        
        # 替换提示词中的占位符
        prompt = prompt.replace('$session_path', session_folder_path)
        prompt = prompt.replace('$save_session_path', save_session_path)
        prompt = prompt.replace('$save_session_name', session_name)
        
        print(prompt)
        with open('prompt.txt', 'w', encoding='utf-8') as f:
            f.write(prompt)
        # import time;time.sleep(35000)
        # 最多尝试3次
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            console.print(f"🤖 第 {attempt} 次AI分析尝试...", style="blue")
            # 删除save_session_path及其子目录
            if Path(save_session_path).exists():
                shutil.rmtree(save_session_path)
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
"""

async def failed_analysis_function():
    """AI分析失败的占位函数"""
    return {{
        "success": False,
        "error": "AI分析失败，请检查录制数据并重试",
        "session_path": "{session_folder_path}"
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