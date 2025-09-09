"""
函数执行器
支持执行AI生成的函数代码并录制执行过程
"""

import asyncio
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console

console = Console()

class FunctionExecutor:
    """函数执行器，支持动态执行AI生成的函数代码"""
    
    def __init__(self):
        pass
    
    async def execute_with_recording(
        self,
        function_code: str,
        function_params: Dict[str, Any],
        recording_output_dir: str,
        session_name: str = "test_execution"
    ) -> Dict[str, Any]:
        """
        执行函数代码字符串并录制执行过程
        
        Args:
            function_code: AI生成的函数代码字符串
            function_params: 函数执行参数
            recording_output_dir: 录制数据保存目录
            session_name: 本次执行会话名称
            
        Returns:
            Dict: {
                "execution_result": 函数执行返回值,
                "recording_session_path": 录制数据保存路径,
                "success": bool,
                "error": 错误信息(如果有),
                "final_screenshot": 最终截图路径,
                "final_html": 最终页面HTML内容,
                "execution_time": 执行耗时
            }
        """
        console.print(f"🚀 开始执行函数并录制过程: {session_name}")
        start_time = datetime.now()
        
        # 确保输出目录存在
        output_dir = Path(recording_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "execution_result": None,
            "recording_session_path": None,
            "success": False,
            "error": None,
            "final_screenshot": None,
            "final_html": None,
            "execution_time": 0
        }
        
        try:
            # 1. 验证和准备函数代码
            console.print("🔍 验证函数代码...")
            prepared_code, function_name = self._prepare_function_code(function_code)
            console.print(f"✅ 函数代码已准备，函数名: {function_name}")
            
            # 2. 创建临时模块执行代码
            console.print("📝 创建执行环境...")
            execution_result = await self._execute_function_with_recording(
                prepared_code, 
                function_name, 
                function_params,
                str(output_dir),
                session_name
            )
            
            result.update(execution_result)
            result["success"] = True
            console.print("✅ 函数执行和录制完成")
            
        except Exception as e:
            error_msg = f"执行失败: {str(e)}"
            console.print(f"❌ {error_msg}", style="red")
            console.print(f"❌ 错误详情: {traceback.format_exc()}", style="dim red")
            result["error"] = error_msg
            result["success"] = False
        
        finally:
            # 计算执行时间
            end_time = datetime.now()
            result["execution_time"] = (end_time - start_time).total_seconds()
            console.print(f"⏱️ 总执行时间: {result['execution_time']:.2f}秒")
        
        return result
    
    def _prepare_function_code(self, function_code: str) -> tuple[str, str]:
        """
        准备和验证函数代码
        
        Returns:
            tuple: (准备好的代码, 函数名)
        """
        # 验证代码语法
        try:
            compile(function_code, '<string>', 'exec')
        except SyntaxError as e:
            raise ValueError(f"函数代码语法错误: {e}")
        
        # 提取函数名（简单的正则匹配）
        import re
        function_match = re.search(r'async\s+def\s+(\w+)\s*\(', function_code)
        if not function_match:
            # 尝试匹配同步函数
            function_match = re.search(r'def\s+(\w+)\s*\(', function_code)
        
        if not function_match:
            raise ValueError("无法从代码中提取函数名")
        
        function_name = function_match.group(1)
        
        # 确保代码包含必要的导入（简化版，因为用户会使用我们的接口）
        required_imports = [
            "import asyncio",
            "from typing import Dict, Any, Optional",
            "from pathlib import Path"
        ]
        
        # 检查是否已包含必要导入，如果没有则添加
        prepared_code = function_code
        for import_stmt in required_imports:
            if import_stmt not in prepared_code:
                prepared_code = import_stmt + "\n" + prepared_code
        
        return prepared_code, function_name
    
    async def _execute_function_with_recording(
        self,
        function_code: str,
        function_name: str,
        function_params: Dict[str, Any],
        output_dir: str,
        session_name: str
    ) -> Dict[str, Any]:
        """
        在录制环境中执行函数
        """
        console.print(f"🎬 开始录制执行过程...")
        
        # 创建临时文件保存函数代码
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(function_code)
            tmp_module_path = tmp_file.name
        
        try:
            # 动态导入临时模块
            import importlib.util
            spec = importlib.util.spec_from_file_location("temp_module", tmp_module_path)
            temp_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(temp_module)
            
            # 获取函数对象
            if not hasattr(temp_module, function_name):
                raise ValueError(f"函数 {function_name} 在生成的代码中不存在")
            
            target_function = getattr(temp_module, function_name)
            
            # 执行函数并记录结果
            console.print(f"⚡ 开始执行函数 {function_name}...")
            console.print(f"📋 执行参数: {function_params}")
            
            # 执行函数（支持同步和异步）
            console.print("🚀 执行AI生成的函数...")
            if asyncio.iscoroutinefunction(target_function):
                execution_result = await target_function(**function_params)
            else:
                execution_result = target_function(**function_params)
            
            console.print(f"✅ 函数执行完成")
            console.print(f"📊 执行结果: {execution_result}")
            
            # 尝试从执行结果中提取录制信息
            recording_data = None
            if isinstance(execution_result, dict) and 'recording_info' in execution_result:
                recording_data = execution_result['recording_info']
                console.print("📹 检测到录制数据")
            
            return {
                "execution_result": execution_result,
                "recording_session_path": output_dir,
                "recording_data": recording_data,
                "success": True
            }
            
        except Exception as e:
            console.print(f"❌ 函数执行失败: {e}", style="red")
            raise
        
        finally:
            # 清理临时文件
            try:
                Path(tmp_module_path).unlink()
            except:
                pass
