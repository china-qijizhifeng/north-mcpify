#!/usr/bin/env python3
"""
智能自动化API生成平台 - 交互式启动器
直接启动进入交互模式
"""

import asyncio
from src.cli.interactive import InteractiveCLI

if __name__ == "__main__":
    # 直接启动交互式CLI
    cli = InteractiveCLI()
    asyncio.run(cli.run())