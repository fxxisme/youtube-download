#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube视频批量下载工具（仅下载视频，不转换）
支持从文本文件读取链接列表，批量下载视频文件
每个视频创建独立目录，包含视频文件、描述、缩略图等
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re
import json

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


class YouTubeVideoDownloader:
    def __init__(self, output_dir="./videos", quality="best", max_workers=3, progress_hooks=None, cancel_event=None):
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

    def setup_logging(self):
        """设置日志配置，仅输出到流（控制台/GUI）"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def find_ffmpeg(self):
        """
        查找FFmpeg可执行文件。
        优先顺序:
        1. 如果是打包状态，查找捆绑的FFmpeg。
        2. 如果是开发环境，查找项目内的ffmpeg目录。
        3. 查找系统PATH中的ffmpeg。
        """
        import shutil

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundle_dir = Path(sys._MEIPASS)
            ffmpeg_exe = bundle_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
            if ffmpeg_exe.is_file():
                self.print_colored(f"🔧 使用捆绑的FFmpeg: {ffmpeg_exe}", Fore.BLUE)
                return str(ffmpeg_exe.parent)
        
        local_path = Path("./ffmpeg/bin/ffmpeg.exe")
        if local_path.is_file():
            self.print_colored(f"🔧 使用本地开发的FFmpeg: {local_path.resolve()}", Fore.BLUE)
            return str(local_path.parent.resolve())

        if shutil.which('ffmpeg'):
            self.print_colored("🔧 在系统PATH中找到FFmpeg。", Fore.BLUE)
            return None

        self.print_colored("⚠️ 未找到FFmpeg，视频合并可能会失败。", Fore.YELLOW)
        return None

    def setup_ydl_opts(self, video_dir):
        """配置yt-dlp选项，针对特定视频目录"""
        quality_map = {
            'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
            '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
            '4k': 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best[height<=2160]',
            'worst': 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst',
        }
        
        opts = {
            'format': quality_map.get(self.quality, self.quality),
            'outtmpl': str(video_dir / '%(title)s.%(ext)s'),
            'ignoreerrors': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'writeinfojson': True,
            'writedescription': True,
            'writethumbnail': True,
            'writeannotations': False,
            'progress_hooks': self.progress_hooks,
        }
        
        ffmpeg_location = self.find_ffmpeg()
        if ffmpeg_location:
            opts['ffmpeg_location'] = ffmpeg_location
            
        return opts
    
    def clean_filename(self, filename):
        """清理文件名中的非法字符，用于创建目录名"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'[^\w\s\-\.\(\)\[\]&]', '_', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        return filename[:100].rstrip()
    
    def create_video_directory(self, title, uploader):
        """为视频创建专用目录"""
        clean_title = self.clean_filename(title)
        clean_uploader = self.clean_filename(uploader) if uploader else "Unknown"
        dir_name = f"{clean_uploader} - {clean_title}"
        video_dir = self.output_dir / dir_name
        
        counter = 1
        original_dir = video_dir
        while video_dir.exists():
            video_dir = Path(f"{original_dir} ({counter})")
            counter += 1
        
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir
    
    def save_video_metadata(self, video_dir, info):
        """保存视频元数据到单独文件"""
        try:
            metadata = {
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'url': info.get('webpage_url', ''),
            }
            metadata_file = video_dir / "video_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"保存元数据失败: {e}")
    
    def create_readme_file(self, video_dir, info):
        """为视频目录创建README文件"""
        try:
            readme_file = video_dir / "README.md"
            title = info.get('title', 'Unknown')
            description = info.get('description', '暂无描述')
            
            with open(readme_file, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n")
                f.write(f"**频道:** {info.get('uploader', 'Unknown')}\n\n")
                f.write(f"**原始链接:** {info.get('webpage_url', '')}\n\n")
                f.write("## 视频描述\n\n")
                f.write(f"{description[:1000]}{'...' if len(description) > 1000 else ''}\n")
            
        except Exception as e:
            self.logger.warning(f"创建README失败: {e}")
    
    def print_colored(self, text, color=Fore.WHITE, style=Style.RESET_ALL):
        """彩色打印"""
        if USE_COLOR:
            print(f"{color}{style}{text}{Style.RESET_ALL}")
        else:
            print(text)
    
    def download_single_video(self, url):
        """下载单个视频"""
        if self.cancel_event and self.cancel_event.is_set():
            self.print_colored(f"⚠️ 下载已取消 (跳过): {url}", Fore.YELLOW)
            return 'cancelled'

        url = url.strip()
        if not url or url.startswith('#'):
            return None
        
        try:
            with yt_dlp.YoutubeDL({'ignoreerrors': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise Exception("无法获取视频信息")
                
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                self.print_colored(f"🎬 准备下载: {title}", Fore.CYAN)
                
                video_dir = self.create_video_directory(title, uploader)
                self.print_colored(f"📁 创建目录: {video_dir.name}", Fore.YELLOW)
                
                ydl_opts = self.setup_ydl_opts(video_dir)
                
                with yt_dlp.YoutubeDL(ydl_opts) as video_ydl:
                    video_ydl.download([url])
                
                self.save_video_metadata(video_dir, info)
                self.create_readme_file(video_dir, info)
                
                self.print_colored(f"✅ 成功: {title}", Fore.GREEN)
                self.logger.info(f"下载成功: {title} -> {video_dir}")
                return True
                
        except yt_dlp.utils.DownloadError as e:
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
    
    def batch_download(self, urls):
        """批量下载"""
        if not urls:
            self.print_colored("❌ 没有找到有效的URL", Fore.RED)
            return
        
        self.print_colored(f"🚀 开始批量下载视频，共 {len(urls)} 个链接", Fore.CYAN, Style.BRIGHT)
        
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
    parser = argparse.ArgumentParser(description="YouTube视频批量下载工具")
    parser.add_argument('input_file', help='包含YouTube链接的文本文件')
    args = parser.parse_args()
    
    downloader = YouTubeVideoDownloader()
    urls = downloader.read_urls_from_file(args.input_file)
    if urls:
        downloader.batch_download(urls)

if __name__ == "__main__":
    main()
