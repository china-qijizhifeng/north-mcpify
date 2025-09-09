"""
基础功能测试
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import json

from src.session.manager import SessionManager

class TestSessionManager(unittest.TestCase):
    """会话管理器测试"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp()
        self.session_manager = SessionManager(self.test_dir)
    
    def tearDown(self):
        """测试后清理"""
        shutil.rmtree(self.test_dir)
    
    def test_list_empty_sessions(self):
        """测试列出空会话列表"""
        sessions = self.session_manager.list_sessions()
        self.assertEqual(len(sessions), 0)
    
    def test_create_and_load_session(self):
        """测试创建和加载会话"""
        # 创建测试会话数据
        session_id = "test_session_001"
        session_dir = Path(self.test_dir) / session_id
        session_dir.mkdir()
        
        test_metadata = {
            "session_id": session_id,
            "timestamp": "2024-01-01T10:00:00",
            "metadata": {
                "name": "测试会话",
                "url": "https://example.com"
            },
            "operations": [],
            "ai_analysis": {
                "analyzed": False
            }
        }
        
        # 保存测试数据
        with open(session_dir / 'metadata.json', 'w') as f:
            json.dump(test_metadata, f)
        
        # 测试加载
        loaded_session = self.session_manager.load_session(session_id)
        self.assertIsNotNone(loaded_session)
        self.assertEqual(loaded_session['session_id'], session_id)
        self.assertEqual(loaded_session['metadata']['name'], '测试会话')
    
    def test_save_analysis(self):
        """测试保存分析结果"""
        # 创建测试会话
        session_id = "test_session_002"
        session_dir = Path(self.test_dir) / session_id
        session_dir.mkdir()
        
        metadata = {
            "session_id": session_id,
            "ai_analysis": {}
        }
        
        with open(session_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f)
        
        # 测试保存分析结果
        analysis_result = {
            "suggested_parameters": [
                {
                    "name": "username",
                    "type": "str",
                    "description": "用户名",
                    "required": True
                }
            ],
            "function_signature": "def test_function(username: str) -> Dict"
        }
        
        success = self.session_manager.save_analysis(session_id, analysis_result)
        self.assertTrue(success)
        
        # 验证保存结果
        analysis_file = session_dir / 'ai_analysis.json'
        self.assertTrue(analysis_file.exists())
        
        with open(analysis_file, 'r') as f:
            saved_analysis = json.load(f)
        
        self.assertTrue(saved_analysis['analyzed'])
        self.assertEqual(len(saved_analysis['suggested_parameters']), 1)
        self.assertEqual(saved_analysis['suggested_parameters'][0]['name'], 'username')
    
    def test_function_generation(self):
        """测试函数生成"""
        # 创建包含分析结果的会话
        session_id = "test_session_003"
        session_dir = Path(self.test_dir) / session_id
        session_dir.mkdir()
        
        session_data = {
            "session_id": session_id,
            "metadata": {
                "name": "test_automation",
                "url": "https://example.com"
            },
            "operations": [
                {
                    "step_id": 1,
                    "action": "click",
                    "selector": "#login-btn",
                    "value": ""
                },
                {
                    "step_id": 2,
                    "action": "input",
                    "selector": "#username",
                    "value": "test_user"
                }
            ],
            "ai_analysis": {
                "analyzed": True,
                "suggested_parameters": [
                    {
                        "name": "username",
                        "type": "str",
                        "description": "登录用户名",
                        "required": True
                    }
                ]
            }
        }
        
        with open(session_dir / 'metadata.json', 'w') as f:
            json.dump(session_data, f)
        
        # 测试函数生成
        function_code = self.session_manager.generate_function(session_id)
        
        self.assertIn('def test_automation', function_code)
        self.assertIn('username: str', function_code)
        self.assertIn('async def', function_code)
        self.assertIn('playwright', function_code)

class TestUtilities(unittest.TestCase):
    """工具函数测试"""
    
    def test_clean_function_name(self):
        """测试函数名清理"""
        from src.session.manager import SessionManager
        manager = SessionManager()
        
        # 测试各种输入
        self.assertEqual(manager._clean_function_name("Test Function"), "test_function")
        self.assertEqual(manager._clean_function_name("Login-Demo!"), "logindemo")
        self.assertEqual(manager._clean_function_name("123test"), "automation_123test")
        self.assertEqual(manager._clean_function_name(""), "automation_function")
        self.assertEqual(manager._clean_function_name("用户登录"), "用户登录")  # 中文字符保留

if __name__ == '__main__':
    unittest.main()