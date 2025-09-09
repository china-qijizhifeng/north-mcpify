"""
AI分析引擎
使用大语言模型分析录制会话并生成参数化建议
支持OpenAI格式API调用，可配置BASE_URL和MODEL_NAME
增强支持任务描述和返回值期望
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from openai import OpenAI
from rich.console import Console
from src.utils.config import Config

console = Console()

class AIAnalyzer:
    """AI分析器"""
    
    def __init__(self):
        self.client = None
        self.model_name = None
        self._setup_model()
    
    def _setup_model(self):
        """设置AI模型"""
        try:
            if not Config.validate_ai_config():
                console.print("⚠️  未找到API_KEY环境变量", style="yellow")
                console.print("请在.env文件中设置 API_KEY、BASE_URL 和 MODEL_NAME")
                console.print("示例配置:")
                console.print("  API_KEY=your_api_key_here")
                console.print("  BASE_URL=https://api.openai.com/v1")
                console.print("  MODEL_NAME=gpt-4o")
                return
            
            # 从配置获取参数
            self.model_name = Config.MODEL_NAME
            
            # 初始化OpenAI客户端
            client_kwargs = {
                'api_key': Config.API_KEY,
                'timeout': 600.0,
                'max_retries': 2
            }
            if Config.BASE_URL:
                client_kwargs['base_url'] = Config.BASE_URL
                
            self.client = OpenAI(**client_kwargs)
            
            console.print(Config.get_ai_config_status(), style="green")
            
        except Exception as e:
            console.print(f"❌ AI模型初始化失败: {e}", style="red")
    
    async def analyze_session(self, session_data: Dict) -> Dict[str, Any]:
        """分析会话并生成参数化建议"""
        if not self.client:
            raise ValueError("AI模型未初始化")
        
        console.print("🤖 正在分析会话...")
        
        # 构建分析提示
        prompt = self._build_analysis_prompt(session_data)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "你是一个网页自动化专家，专门分析用户录制的网页操作并将其转化为可参数化的Python函数。你需要特别关注用户的任务描述和期望返回值，以便生成最符合需求的自动化函数。请严格按照JSON格式返回分析结果。"
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            )
            
            result = self._parse_analysis_response(response.choices[0].message.content)
            
            console.print("✅ AI分析完成", style="green")
            return result
            
        except Exception as e:
            console.print(f"❌ AI分析失败: {e}", style="red")
            raise
    
    def _build_analysis_prompt(self, session_data: Dict) -> str:
        """构建分析提示"""
        operations = session_data.get('operations', [])
        metadata = session_data.get('metadata', {})
        task_definition = session_data.get('task_definition', {})
        
        # 基础信息
        prompt = f"""
你是一个网页自动化专家，需要分析用户的网页操作录制会话，并将其转化为可参数化的Python函数。

会话信息:
- 名称: {metadata.get('name', 'Unknown')}
- URL: {metadata.get('url', '')}
- 操作数量: {len(operations)}
"""
        
        # 添加任务描述信息（重要！）
        if task_definition:
            prompt += f"""

🎯 任务定义:
- 任务描述: {task_definition.get('description', '未提供')}
- 期望返回: {task_definition.get('expected_return', {}).get('description', '未指定')}
- 返回类型: {task_definition.get('expected_return', {}).get('type', 'unknown')}
"""
            
        prompt += """

操作序列:
"""
        
        # 添加操作详情
        for i, op in enumerate(operations, 1):
            prompt += f"""
步骤 {i}:
- 动作: {op['action']}
- 选择器: {op['selector']}
- 值: {op.get('value', 'N/A')}
- 文本内容: {op.get('text_content', 'N/A')}
- 页面URL: {op.get('page_url', 'N/A')}
- AI注释: {op.get('ai_annotations', {}).get('intent', 'unknown')}
"""
        
        prompt += """

请基于任务描述和期望返回值分析这些操作，识别可以参数化的部分，并提供以下JSON格式的结果:

{
    "suggested_parameters": [
        {
            "name": "参数名称",
            "type": "参数类型 (str/int/bool/list/dict)",
            "description": "参数描述",
            "default": "默认值或null",
            "required": true/false,
            "inferred_from": "从哪个操作推断出来的"
        }
    ],
    "function_signature": "def function_name(param1: str, param2: int) -> 基于期望返回类型",
    "function_description": "基于任务描述的函数功能描述",
    "return_extraction": {
        "elements": ["需要提取的页面元素的选择器"],
        "method": "提取方法 (text/attribute/multiple_texts/data_structure)",
        "description": "返回值的具体描述"
    },
    "improvements": [
        "改进建议1",
        "改进建议2"
    ]
}

关键分析要点:
1. 基于任务描述识别用户输入的值（如搜索关键词、表单数据等）
2. 根据期望返回值确定需要提取的页面元素
3. 生成符合任务目标的函数名和参数名
4. 考虑错误处理和异常情况
5. 确保返回值类型与用户期望一致
6. 优化选择器的稳定性

请只返回JSON格式的结果，不要包含其他内容。
"""
        
        return prompt
    
    def _parse_analysis_response(self, response_text: str) -> Dict[str, Any]:
        """解析AI分析响应"""
        try:
            # 提取JSON内容
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("未找到有效的JSON内容")
            
            json_content = response_text[start_idx:end_idx]
            result = json.loads(json_content)
            
            # 验证必要字段
            if 'suggested_parameters' not in result:
                result['suggested_parameters'] = []
            
            if 'function_signature' not in result:
                result['function_signature'] = 'def automation_function() -> Dict'
            
            if 'return_extraction' not in result:
                result['return_extraction'] = {
                    'elements': [],
                    'method': 'text',
                    'description': '默认返回操作结果'
                }
            
            return result
            
        except Exception as e:
            console.print(f"⚠️  解析AI响应失败: {e}", style="yellow")
            # 返回基础结构
            return {
                'suggested_parameters': [],
                'function_signature': 'def automation_function() -> Dict',
                'function_description': 'AI分析失败，使用默认配置',
                'return_extraction': {
                    'elements': [],
                    'method': 'text', 
                    'description': '默认返回操作结果'
                },
                'improvements': ['请手动检查和优化代码']
            }
    
    
    async def refine_analysis(self, session_data: Dict, user_instruction: str) -> Dict[str, Any]:
        """根据用户指令优化分析结果"""
        if not self.client:
            console.print("⚠️  AI模型未初始化，无法优化", style="yellow")
            return session_data.get('ai_analysis', {})
        
        current_analysis = session_data.get('ai_analysis', {})
        task_definition = session_data.get('task_definition', {})
        
        prompt = f"""
用户对当前的自动化函数分析结果有以下优化要求：
"{user_instruction}"

原始任务定义:
{json.dumps(task_definition, ensure_ascii=False, indent=2)}

当前分析结果：
{json.dumps(current_analysis, ensure_ascii=False, indent=2)}

会话操作数据：
{json.dumps(session_data.get('operations', []), ensure_ascii=False, indent=2)}

请根据用户的要求，优化分析结果。返回完整的JSON格式结果：

{{
    "suggested_parameters": [...],
    "function_signature": "优化后的函数签名",
    "function_description": "函数描述",
    "return_extraction": {{
        "elements": ["需要提取的页面元素选择器"],
        "method": "提取方法",
        "description": "返回值描述"
    }},
    "improvements": ["本次优化的改进点"],
    "changes": "本次修改的具体说明"
}}

只返回JSON格式结果，不要包含其他内容。
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个网页自动化专家，根据用户的反馈优化自动化函数的分析结果。请严格按照JSON格式返回优化后的结果。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
            )
            
            result = self._parse_analysis_response(response.choices[0].message.content)
            return result
            
        except Exception as e:
            console.print(f"❌ 优化分析失败: {e}", style="red")
            return current_analysis