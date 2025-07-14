import customtkinter as ctk
from tkinter import filedialog
import threading
import queue
import os
from pathlib import Path
import shutil
import sys

# 确保src目录在sys.path中
try:
    from src.youtube_to_mp3 import YouTubeToMP3
    from src.youtube_video_downloader import YouTubeVideoDownloader
except ImportError:
    current_dir = Path(__file__).parent
    parent_dir = current_dir.parent
    sys.path.insert(0, str(parent_dir))
    from src.youtube_to_mp3 import YouTubeToMP3
    from src.youtube_video_downloader import YouTubeVideoDownloader

# --- UI ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

QUALITY_MAP = {
    "最高画质": "best", "1080p": "1080p", "720p": "720p",
    "480p": "best[height<=480][ext=mp4]/best[height<=480]", "最低画质": "worst"
}

class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader")
        self.geometry("850x750")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self.setup_input_frame()
        self.setup_action_frame()
        self.setup_log_frame()

        self.log_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.after(100, self.process_log_queue)

    def setup_input_frame(self):
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsew")
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(1, weight=1)

        url_header_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        url_header_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=(10,0), sticky="ew")
        url_header_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(url_header_frame, text="输入URL(每行一个):").pack(side="left")
        self.import_button = ctk.CTkButton(url_header_frame, text="导入文件...", width=100, command=self.import_urls_from_file)
        self.import_button.pack(side="right")

        self.url_textbox = ctk.CTkTextbox(input_frame, wrap=ctk.WORD, font=("Arial", 13))
        self.url_textbox.grid(row=1, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="nsew")
        
        path_frame = ctk.CTkFrame(input_frame)
        path_frame.grid(row=2, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        path_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(path_frame, text="保存位置:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.save_path_var = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.path_entry = ctk.CTkEntry(path_frame, textvariable=self.save_path_var)
        self.path_entry.grid(row=0, column=1, padx=0, pady=10, sticky="ew")
        self.browse_button = ctk.CTkButton(path_frame, text="浏览...", width=100, command=self.browse_save_path)
        self.browse_button.grid(row=0, column=2, padx=10, pady=10)

    def setup_action_frame(self):
        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        action_frame.grid_columnconfigure((0, 1), weight=1)

        self.download_audio_button = ctk.CTkButton(action_frame, text="下载音频", command=lambda: self.start_download('mp3'))
        self.download_audio_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        video_download_frame = ctk.CTkFrame(action_frame)
        video_download_frame.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        video_download_frame.grid_columnconfigure(0, weight=1)
        
        self.download_video_button = ctk.CTkButton(video_download_frame, text="下载视频", command=lambda: self.start_download('video'))
        self.download_video_button.grid(row=0, column=0, sticky="ew")
        
        self.quality_menu = ctk.CTkOptionMenu(video_download_frame, values=list(QUALITY_MAP.keys()))
        self.quality_menu.set("最高画质")
        self.quality_menu.grid(row=0, column=1, padx=10, pady=5)

        self.status_label = ctk.CTkLabel(action_frame, text="状态: 空闲", anchor="w")
        self.status_label.grid(row=1, column=0, padx=10, pady=(5,0), sticky="ew")
        
        self.cancel_button = ctk.CTkButton(action_frame, text="取消下载", command=self.cancel_download, state="disabled", fg_color="red", hover_color="darkred")
        self.cancel_button.grid(row=1, column=1, padx=10, pady=(5,0), sticky="e")
        
        self.progress_bar = ctk.CTkProgressBar(action_frame, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, columnspan=2, padx=10, pady=(5,10), sticky="ew")

    def setup_log_frame(self):
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(log_frame, wrap=ctk.WORD, state='disabled', font=("Arial", 12))
        self.log_text.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    def import_urls_from_file(self):
        file_path = filedialog.askopenfilename(title="选择URL文本文件", filetypes=(("Text files", "*.txt"), ("All files", "*.*")))
        if not file_path: return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.url_textbox.delete("1.0", ctk.END)
                self.url_textbox.insert("1.0", f.read())
            self.log_message(f"成功从 '{Path(file_path).name}' 导入URL。")
        except Exception as e:
            self.log_message(f"错误: 无法读取文件 '{file_path}': {e}")

    def browse_save_path(self):
        directory = filedialog.askdirectory(initialdir=self.save_path_var.get())
        if directory: self.save_path_var.set(directory)

    def log_message(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert(ctk.END, message + "\n")
        self.log_text.see(ctk.END)
        self.log_text.configure(state='disabled')

    def process_log_queue(self):
        try:
            while True:
                msg_type, value = self.log_queue.get_nowait()
                if msg_type == "log": self.log_message(value)
                elif msg_type == "progress": self.progress_bar.set(value)
                elif msg_type == "status": self.status_label.configure(text=f"状态: {value}")
                elif msg_type == "ui_state_idle": self.set_ui_state_idle()
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_log_queue)

    def set_ui_state_downloading(self):
        self.url_textbox.configure(state="disabled")
        self.path_entry.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.download_audio_button.configure(state="disabled")
        self.download_video_button.configure(state="disabled")
        self.quality_menu.configure(state="disabled")
        self.cancel_button.configure(state="normal")

    def set_ui_state_idle(self):
        self.url_textbox.configure(state="normal")
        self.path_entry.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.import_button.configure(state="normal")
        self.download_audio_button.configure(state="normal")
        self.download_video_button.configure(state="normal")
        self.quality_menu.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def start_download(self, download_type):
        raw_text = self.url_textbox.get("1.0", ctk.END)
        urls = [line.strip() for line in raw_text.splitlines() if line.strip() and not line.startswith('#')]
        if not urls:
            self.log_message("错误: 请输入至少一个有效的URL。")
            return

        self.cancel_event.clear()
        self.set_ui_state_downloading()
        self.progress_bar.set(0)
        self.log_message(f"检测到 {len(urls)} 个URL，准备下载...")
        self.status_label.configure(text="状态: 准备中...")

        video_quality_key = QUALITY_MAP.get(self.quality_menu.get(), "best") if download_type == 'video' else None

        threading.Thread(
            target=self.run_download, 
            args=(download_type, urls, self.save_path_var.get(), video_quality_key, self.cancel_event),
            daemon=True
        ).start()

    def cancel_download(self):
        self.log_message("正在请求取消下载...")
        self.status_label.configure(text="状态: 正在取消...")
        self.cancel_button.configure(state="disabled")
        self.cancel_event.set()

    def run_download(self, download_type, urls, save_path, quality, cancel_event):
        final_status = "已完成"
        try:
            downloader_class = YouTubeToMP3 if download_type == 'mp3' else YouTubeVideoDownloader
            downloader_params = {
                "output_dir": save_path,
                "progress_hooks": [self.progress_hook],
                "cancel_event": cancel_event
            }
            if download_type == 'video':
                downloader_params['quality'] = quality
            
            downloader = downloader_class(**downloader_params)
            downloader.print_colored = lambda text, *args, **kwargs: self.log_queue.put(("log", str(text)))

            self.log_queue.put(("status", f"开始批量下载 {len(urls)} 个项目..."))
            downloader.batch_download(urls)
            
            if cancel_event.is_set():
                final_status = "已取消"
            self.log_queue.put(("log", f"--- 任务结束 ---"))

        except Exception as e:
            final_status = f"错误: {e}"
            self.log_queue.put(("log", f"发生严重错误: {e}"))
        finally:
            self.log_queue.put(("status", final_status))
            self.log_queue.put(("ui_state_idle", None))
            self.log_queue.put(("progress", 0.0))

    def progress_hook(self, d):
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadError("下载已被用户取消")

        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                self.log_queue.put(("progress", d['downloaded_bytes'] / total))
                filename = Path(d.get('filename', '')).name
                self.log_queue.put(("status", f"下载中: {filename[:30]}..."))
        elif d['status'] == 'finished':
            self.log_queue.put(("progress", 1.0))
            if d.get('postprocessor'):
                self.log_queue.put(("status", f"处理中: {d['postprocessor']}..."))

if __name__ == "__main__":
    if not os.path.exists("./ffmpeg/bin/ffmpeg.exe") and not shutil.which("ffmpeg"):
        print("警告: 未找到ffmpeg，MP3转换和部分视频下载可能失败。")
    
    # yt-dlp的依赖需要导入，即使没有直接使用
    try:
        import yt_dlp
    except ImportError:
        print("错误: 找不到 yt-dlp 库。请运行 'pip install yt-dlp' 安装。")
        sys.exit(1)

    app = DownloaderApp()
    app.mainloop()