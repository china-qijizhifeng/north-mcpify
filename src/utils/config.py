"""
配置管理模块
加载和验证环境变量配置
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

class Config:
    """配置管理类"""
    
    # AI模型配置
    API_KEY: Optional[str] = os.getenv('API_KEY') or os.getenv('OPENAI_API_KEY')
    BASE_URL: Optional[str] = os.getenv('BASE_URL') or os.getenv('OPENAI_BASE_URL')
    MODEL_NAME: str = os.getenv('MODEL_NAME', 'gpt-4o')
    
    # 录制配置
    DEFAULT_BROWSER: str = os.getenv('DEFAULT_BROWSER', 'chromium')
    DEFAULT_VIEWPORT_WIDTH: int = int(os.getenv('DEFAULT_VIEWPORT_WIDTH', '1920'))
    DEFAULT_VIEWPORT_HEIGHT: int = int(os.getenv('DEFAULT_VIEWPORT_HEIGHT', '1080'))
    
    # 存储配置
    SESSIONS_DIR: str = os.getenv('SESSIONS_DIR', 'sessions')
    FUNCTIONS_OUTPUT_DIR: str = os.getenv('FUNCTIONS_OUTPUT_DIR', 'generated_functions')
    
    @classmethod
    def validate_ai_config(cls) -> bool:
        """验证AI配置是否完整"""
        return cls.API_KEY is not None
    
    @classmethod
    def get_ai_config_status(cls) -> str:
        """获取AI配置状态描述"""
        if not cls.API_KEY:
            return "❌ API_KEY未配置"
        
        status = f"✅ Model: {cls.MODEL_NAME}"
        if cls.BASE_URL:
            status += f", Base URL: {cls.BASE_URL}"
        
        return status
    
    @classmethod
    def ensure_directories(cls):
        """确保必要的目录存在"""
        Path(cls.SESSIONS_DIR).mkdir(exist_ok=True)
        Path(cls.FUNCTIONS_OUTPUT_DIR).mkdir(exist_ok=True)

# 确保目录存在
Config.ensure_directories()