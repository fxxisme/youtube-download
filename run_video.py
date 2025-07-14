#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube视频下载工具启动脚本
专门用于下载视频文件（不转换为音频）
"""

import sys
import os
from pathlib import Path

# 添加src目录到Python路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

try:
    from youtube_video_downloader import main
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保已安装所有依赖: pip install -r requirements.txt")
    sys.exit(1)

if __name__ == "__main__":
    # 设置默认参数，方便在VS Code中调试
    if len(sys.argv) == 1:
        # 如果没有提供参数，使用默认的链接文件
        default_links_file = "data/links.txt"
        if os.path.exists(default_links_file):
            sys.argv.append(default_links_file)
            print(f"🎯 使用默认链接文件: {default_links_file}")
            print("🎬 模式: 视频下载（不转换音频）")
        else:
            print(f"❌ 请创建链接文件: {default_links_file}")
            print("或者使用命令行参数: python run_video.py your_links.txt")
            sys.exit(1)
    
    # 运行主程序
    main()