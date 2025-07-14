#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import os

# 读取README文件
def read_readme():
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "YouTube转MP3批量下载工具"

# 读取requirements文件
def read_requirements():
    try:
        with open("requirements.txt", "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return ["yt-dlp>=2023.12.30", "colorama>=0.4.6"]

setup(
    name="youtube-to-mp3",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="YouTube视频批量转MP3工具",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/youtube-to-mp3",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
        "Topic :: Internet :: WWW/HTTP",
    ],
    python_requires=">=3.7",
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "youtube-to-mp3=youtube_to_mp3:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)