import asyncio
from src.session.manager import SessionManager

async def main():
    session_manager = SessionManager()
    result = await session_manager.trigger_ai_analysis(
        session_folder_path='/Users/kausal/north_mcpify/sessions/session_20250909_150856',
        task_description='arxiv获取关于某个话题的在某个时间范围的前10篇论文',
        output_format_requirements='希望以list of dict形式返回，每个元素包含论文标题，链接和摘要',
        save_function_path=None
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())