#!/usr/bin/env python3
"""
智能自动化API生成平台
主入口文件 - 交互式界面
"""

import asyncio
from src.cli.interactive import InteractiveCLI

async def main():
    """主函数"""
    cli = InteractiveCLI()
    await cli.run()

if __name__ == "__main__":
    asyncio.run(main())