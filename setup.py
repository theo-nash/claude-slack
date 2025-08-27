"""
Setup script for Claude-Slack API package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="claude-slack-api",
    version="4.1.0",
    author="Claude-Slack Team",
    description="Clean infrastructure API for AI agent knowledge management with Qdrant",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/theo-nash/claude-slack",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "qdrant-client>=1.7.0",
        "aiosqlite>=0.19.0",
        "sentence-transformers>=2.2.0",
        "numpy>=1.24.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0.0",
            "mypy>=1.0.0",
        ],
        "mcp": [
            "mcp>=1.0.0",
            "pyyaml>=6.0",
        ]
    }
)