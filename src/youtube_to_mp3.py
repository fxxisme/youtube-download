#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube转MP3批量下载工具
支持从文本文件读取链接列表，批量转换为MP3音频文件
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re

try:
    import yt_dlp
except ImportError:
    print("❌ 请先安装yt-dlp: pip install yt-dlp")
    sys.exit(1)

try:
    from colorama import init, Fore, Style
    init()
    USE_COLOR = True
except ImportError:
    USE_COLOR = False
    # 定义空的颜色常量
    class Fore:
        RED = GREEN = YELLOW = BLUE = CYAN = WHITE = ""
    class Style:
        RESET_ALL = BRIGHT = ""


class YouTubeToMP3:
    def __init__(self, output_dir="./downloads", quality="192", max_workers=3, progress_hooks=None, cancel_event=None):
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.max_workers = max_workers
        self.progress_hooks = progress_hooks or []
        self.cancel_event = cancel_event
        self.success_count = 0
        self.failed_count = 0
        self.cancelled_count = 0
        self.failed_urls = []
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.setup_logging()
        self.setup_ydl_opts()
    
    def setup_logging(self):
        """设置日志配置"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"youtube_to_mp3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_ydl_opts(self):
        """配置yt-dlp选项"""
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': self.quality,
            }],
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'ignoreerrors': True,
            'no_warnings': True,
            'extractaudio': True,
            'audioformat': 'mp3',
            'embed_subs': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'progress_hooks': self.progress_hooks,
        }
        
        # 检查是否需要指定FFmpeg路径
        ffmpeg_path = self.find_ffmpeg()
        if ffmpeg_path:
            self.ydl_opts['ffmpeg_location'] = ffmpeg_path
    
    def find_ffmpeg(self):
        """查找FFmpeg可执行文件"""
        import shutil
        
        # 首先检查系统PATH中是否有ffmpeg
        if shutil.which('ffmpeg'):
            return None
        
        # 检查常见的安装位置
        common_paths = [
            'C:\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
            'C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe',
            '.\\ffmpeg.exe',
            '.\\bin\\ffmpeg.exe',
            '.\\ffmpeg\\bin\\ffmpeg.exe',
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                self.print_colored(f"🔧 找到FFmpeg: {path}", Fore.BLUE)
                return os.path.dirname(path)
        
        # 如果都没找到，提示用户
        self.print_colored("⚠️ 未找到FFmpeg，请确保已正确安装", Fore.YELLOW)
        self.print_colored("   可以下载FFmpeg并放在以下位置之一：", Fore.YELLOW)
        for path in common_paths:
            self.print_colored(f"   - {path}", Fore.YELLOW)
        
        return None
    
    def print_colored(self, text, color=Fore.WHITE, style=Style.RESET_ALL):
        """彩色打印"""
        if USE_COLOR:
            print(f"{color}{style}{text}{Style.RESET_ALL}")
        else:
            print(text)
    
    def clean_filename(self, filename):
        """清理文件名中的非法字符"""
        # 移除或替换非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename.strip()
    
    def download_single_video(self, url):
        """下载单个视频"""
        if self.cancel_event and self.cancel_event.is_set():
            self.print_colored(f"⚠️ 下载已取消 (跳过): {url}", Fore.YELLOW)
            return 'cancelled'

        url = url.strip()
        if not url or url.startswith('#'):
            return None
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("无法获取视频信息")
                
                title = info.get('title', 'Unknown')
                self.print_colored(f"🎵 开始下载: {title}", Fore.CYAN)
                
                ydl.download([url])
                
                self.print_colored(f"✅ 成功: {title}", Fore.GREEN)
                self.logger.info(f"下载成功: {title} - {url}")
                return True
                
        except yt_dlp.utils.DownloadError as e:
            # 由GUI的progress_hook触发的取消异常
            if "已被用户取消" in str(e):
                self.print_colored(f"🛑 下载已取消: {url}", Fore.YELLOW)
                return 'cancelled'
            else:
                self.print_colored(f"❌ 失败: {url} - {e}", Fore.RED)
                self.logger.error(f"下载失败: {url} - {e}")
                return False
        except Exception as e:
            self.print_colored(f"❌ 失败: {url} - {e}", Fore.RED)
            self.logger.error(f"下载失败: {url} - {e}")
            return False
    
    def read_urls_from_file(self, file_path):
        """从文件读取URL列表"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            self.print_colored(f"❌ 文件不存在: {file_path}", Fore.RED)
            return []
        except Exception as e:
            self.print_colored(f"❌ 读取文件失败: {e}", Fore.RED)
            return []
    
    def batch_download(self, urls):
        """批量下载"""
        if not urls:
            self.print_colored("❌ 没有找到有效的URL", Fore.RED)
            return
        
        self.print_colored(f"🚀 开始批量下载，共 {len(urls)} 个链接", Fore.CYAN, Style.BRIGHT)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {executor.submit(self.download_single_video, url): url for url in urls}
            
            for future in as_completed(future_to_url):
                if self.cancel_event and self.cancel_event.is_set():
                    self.print_colored("🛑 检测到取消信号，停止处理后续任务。", Fore.YELLOW)
                    break

                url = future_to_url[future]
                try:
                    result = future.result()
                    if result == 'cancelled':
                        self.cancelled_count += 1
                    elif result:
                        self.success_count += 1
                    else:
                        self.failed_count += 1
                        self.failed_urls.append(url)
                except Exception as e:
                    self.failed_count += 1
                    self.failed_urls.append(url)
                    self.logger.error(f"处理URL时发生异常: {url} - {e}")
        
        self.print_summary()
    
    def print_summary(self):
        """打印下载总结"""
        print("\n" + "="*60)
        self.print_colored("📊 下载总结", Fore.CYAN, Style.BRIGHT)
        self.print_colored(f"✅ 成功: {self.success_count}", Fore.GREEN)
        self.print_colored(f"❌ 失败: {self.failed_count}", Fore.RED)
        if self.cancelled_count > 0:
            self.print_colored(f"⚠️ 取消: {self.cancelled_count}", Fore.YELLOW)
        
        if self.failed_urls:
            self.print_colored("\n❌ 失败的链接:", Fore.RED)
            for url in self.failed_urls:
                self.print_colored(f"   - {url}", Fore.RED)
            
            failed_file = self.output_dir / "failed_urls.txt"
            with open(failed_file, 'w', encoding='utf-8') as f:
                for url in self.failed_urls:
                    f.write(f"{url}\n")
            self.print_colored(f"💾 失败链接已保存到: {failed_file}", Fore.YELLOW)
        
        print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube视频批量转MP3工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python youtube_to_mp3.py links.txt
  python youtube_to_mp3.py links.txt -o ./music -q 320 -t 5
  
links.txt文件格式:
  https://www.youtube.com/watch?v=dQw4w9WgXcQ
  https://youtu.be/9bZkp7q19f0
  # 这是注释，会被忽略
  https://www.youtube.com/playlist?list=PLxxxxxx
        """
    )
    
    parser.add_argument('input_file', help='包含YouTube链接的文本文件')
    parser.add_argument('-o', '--output', default='./downloads', 
                       help='输出目录 (默认: ./downloads)')
    parser.add_argument('-q', '--quality', choices=['128', '192', '320'], 
                       default='192', help='音质质量 (默认: 192 kbps)')
    parser.add_argument('-t', '--threads', type=int, default=3, 
                       help='并发线程数 (默认: 3)')
    parser.add_argument('--version', action='version', version='YouTube转MP3工具 v1.0')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    # 创建下载器
    downloader = YouTubeToMP3(
        output_dir=args.output,
        quality=args.quality,
        max_workers=args.threads
    )
    
    # 读取URL列表
    urls = downloader.read_urls_from_file(args.input_file)
    
    if not urls:
        print("❌ 没有找到有效的YouTube链接")
        sys.exit(1)
    
    # 开始批量下载
    try:
        downloader.batch_download(urls)
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断了下载过程")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()