"""
安装脚本
"""

from setuptools import setup, find_packages


setup(
    name="web-automation-platform",
    version="0.1.0",
    author="Web Automation Team",
    description="智能自动化API生成平台 - 将网页操作转化为Python函数",
    long_description="智能自动化API生成平台 - 将网页操作转化为Python函数",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "playwright>=1.40.0",
        "click>=8.1.7",
        "aiofiles>=23.2.1",
        "pydantic>=2.5.1",
        "python-dotenv>=1.0.0",
        "google-generativeai>=0.3.2",
        "rich>=13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "webautomation=main:cli",
        ],
    },
)