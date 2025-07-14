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
    
    def clean_filename(self, filename):
        """清理文件名中的非法字符，用于创建目录名"""
        # 移除或替换非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 替换一些特殊字符为下划线
        filename = re.sub(r'[^\w\s\-\.\(\)\[\]&]', '_', filename)
        # 移除多余空格并限制长度
        filename = re.sub(r'\s+', ' ', filename).strip()
        if len(filename) > 100:  # 目录名不要太长
            filename = filename[:100].rstrip()
        return filename
    
    def create_video_directory(self, title, uploader):
        """为视频创建专用目录"""
        # 清理标题作为目录名
        clean_title = self.clean_filename(title)
        clean_uploader = self.clean_filename(uploader) if uploader else "Unknown"
        
        # 创建目录名：频道名 - 视频标题
        dir_name = f"{clean_uploader} - {clean_title}"
        video_dir = self.output_dir / dir_name
        
        # 确保目录唯一性
        counter = 1
        original_dir = video_dir
        while video_dir.exists():
            video_dir = Path(f"{original_dir} ({counter})")
            counter += 1
        
        # 创建目录
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir
    
    def setup_ydl_opts(self, video_dir):
        """配置yt-dlp选项，针对特定视频目录"""
        # 质量选择映射
        quality_map = {
            'best': 'best[ext=mp4]/best',
            'worst': 'worst[ext=mp4]/worst',
            '720p': 'best[height<=720][ext=mp4]/best[height<=720]',
            '1080p': 'best[height<=1080][ext=mp4]/best[height<=1080]',
            '4k': 'best[height<=2160][ext=mp4]/best[height<=2160]',
        }
        
        return {
            'format': quality_map.get(self.quality, self.quality),
            'outtmpl': str(video_dir / '%(title)s.%(ext)s'),
            'ignoreerrors': True,
            'no_warnings': True,
            'writesubtitles': True,           # 下载字幕
            'writeautomaticsub': True,        # 下载自动生成字幕
            'writeinfojson': True,            # 保存视频信息到JSON
            'writedescription': True,         # 保存视频描述
            'writethumbnail': True,           # 下载缩略图
            'writeannotations': False,        # 不下载注释（已弃用）
            'progress_hooks': self.progress_hooks,
        }
    
    def save_video_metadata(self, video_dir, info):
        """保存视频元数据到单独文件"""
        try:
            # 创建详细的元数据文件
            metadata = {
                'title': info.get('title', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'subscriber_count': info.get('channel_follower_count', 0),
                'url': info.get('webpage_url', ''),
                'video_id': info.get('id', ''),
                'channel_url': info.get('channel_url', ''),
                'tags': info.get('tags', []),
                'categories': info.get('categories', []),
                'resolution': f"{info.get('width', '?')}x{info.get('height', '?')}",
                'fps': info.get('fps', 'Unknown'),
                'filesize_mb': round(info.get('filesize', 0) / (1024 * 1024), 2) if info.get('filesize') else 'Unknown',
                'download_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # 保存为可读的元数据文件
            metadata_file = video_dir / "video_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # 创建简单的信息文本文件
            info_file = video_dir / "视频信息.txt"
            with open(info_file, 'w', encoding='utf-8') as f:
                f.write(f"视频标题: {metadata['title']}\n")
                f.write(f"上传者: {metadata['uploader']}\n")
                f.write(f"上传日期: {metadata['upload_date']}\n")
                f.write(f"时长: {metadata['duration']//60}:{metadata['duration']%60:02d}\n")
                f.write(f"观看次数: {metadata['view_count']:,}\n")
                f.write(f"点赞数: {metadata['like_count']:,}\n")
                f.write(f"分辨率: {metadata['resolution']}\n")
                f.write(f"文件大小: {metadata['filesize_mb']} MB\n")
                f.write(f"下载时间: {metadata['download_date']}\n")
                f.write(f"原始链接: {metadata['url']}\n")
                if metadata['tags']:
                    f.write(f"标签: {', '.join(metadata['tags'][:10])}\n")  # 只显示前10个标签
                
            self.print_colored(f"💾 已保存元数据: {info_file.name}", Fore.BLUE)
            
        except Exception as e:
            self.logger.warning(f"保存元数据失败: {e}")
    
    def create_readme_file(self, video_dir, info):
        """为视频目录创建README文件"""
        try:
            readme_file = video_dir / "README.md"
            title = info.get('title', 'Unknown')
            uploader = info.get('uploader', 'Unknown')
            description = info.get('description', '暂无描述')
            
            with open(readme_file, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n")
                f.write(f"**频道:** {uploader}\n\n")
                f.write(f"**上传日期:** {info.get('upload_date', 'Unknown')}\n\n")
                f.write(f"**时长:** {info.get('duration', 0)//60}:{info.get('duration', 0)%60:02d}\n\n")
                f.write(f"**观看次数:** {info.get('view_count', 0):,}\n\n")
                f.write(f"**原始链接:** {info.get('webpage_url', '')}\n\n")
                f.write("## 视频描述\n\n")
                f.write(f"{description[:1000]}{'...' if len(description) > 1000 else ''}\n\n")
                f.write("## 文件说明\n\n")
                f.write("- `*.mp4` - 视频文件\n")
                f.write("- `*.jpg/png` - 视频缩略图\n")
                f.write("- `*.description` - 完整视频描述\n")
                f.write("- `*.info.json` - 详细视频信息\n")
                f.write("- `*.vtt/srt` - 字幕文件（如果有）\n")
                f.write("- `video_metadata.json` - 结构化元数据\n")
                f.write("- `视频信息.txt` - 中文视频信息\n")
            
            self.print_colored(f"📋 已创建README: {readme_file.name}", Fore.BLUE)
            
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
            # 首先获取视频信息
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
    parser = argparse.ArgumentParser(
        description="YouTube视频批量下载工具（每个视频独立目录）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python youtube_video_downloader.py links.txt
  python youtube_video_downloader.py links.txt -o ./videos -q 1080p -t 5
  
质量选项:
  best   - 最佳质量（默认）
  worst  - 最低质量（节省空间）
  720p   - 720p分辨率
  1080p  - 1080p分辨率
  4k     - 4K分辨率
  
下载结构:
  videos/
  ├── 频道名 - 视频标题1/
  │   ├── 视频标题1.mp4
  │   ├── 视频标题1.jpg
  │   ├── 视频标题1.description
  │   ├── 视频标题1.info.json
  │   ├── video_metadata.json
  │   ├── 视频信息.txt
  │   └── README.md
  └── 频道名 - 视频标题2/
      └── ...
        """
    )
    
    parser.add_argument('input_file', help='包含YouTube链接的文本文件')
    parser.add_argument('-o', '--output', default='./videos', 
                       help='输出目录 (默认: ./videos)')
    parser.add_argument('-q', '--quality', 
                       choices=['best', 'worst', '720p', '1080p', '4k'], 
                       default='best', help='视频质量 (默认: best)')
    parser.add_argument('-t', '--threads', type=int, default=3, 
                       help='并发线程数 (默认: 3)')
    parser.add_argument('--version', action='version', version='YouTube视频下载工具 v2.0')
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input_file):
        print(f"❌ 输入文件不存在: {args.input_file}")
        sys.exit(1)
    
    # 创建下载器
    downloader = YouTubeVideoDownloader(
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