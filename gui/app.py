"""GUI 主窗口骨架。

ImageRepairApp 只负责:
- 窗口/字体/主题
- 顶部外部引擎状态栏
- 模式切换(单张/批量)
- 共享工具方法(_set_textbox / _open_dir / _get_*_outdir)

两个模式的具体面板和回调由 single_mode.py / batch_mode.py 在 mount_* 时注入。
"""
from __future__ import annotations

import os
import subprocess
import sys  # ★ Bug Fix #1: 原 main.py L806 用 sys.platform 但从未 import
import threading
from typing import Optional

import customtkinter as ctk

from constants import (
    BATCH_SUBFOLDER,
    CJK_FONT_FALLBACK,
    SUPPORTED_EXTS,
    WINDOW_GEOMETRY,
    WINDOW_TITLE,
)
from engine import available_external_engines

from .batch_mode import mount_batch_mode
from .single_mode import mount_single_mode


class ImageRepairApp(ctk.CTk):
    SUPPORTED_EXTS = SUPPORTED_EXTS

    def __init__(self) -> None:
        super().__init__()

        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_GEOMETRY)
        self.resizable(False, False)

        # 设置支持中文的字体 (Windows 默认 CJK 字体)
        try:
            import tkinter as tk  # noqa: F401
            from tkinter import font as tkfont
            for fname in CJK_FONT_FALLBACK:
                try:
                    tkfont.nametofont("TkDefaultFont").configure(family=fname)
                    tkfont.nametofont("TkTextFont").configure(family=fname)
                    break
                except tk.TclError:
                    continue
        except Exception:
            pass

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # --- 引擎状态栏 ---
        # 注:探测 ImageMagick / FFmpeg 在 Windows 上会撞 system32/convert.exe,
        # 单次超时 1.5s,所以**绝不**在 __init__ 同步等结果——窗口先起来,
        # 后台线程探测,回来再回填文字。
        engine_bar = ctk.CTkLabel(
            self, text="外部引擎状态:  ⏳ 检测中...",
            font=("", 12), text_color="gray",
        )
        engine_bar.pack(pady=(10, 0), padx=20, fill="x")
        self._engine_bar = engine_bar  # 保留引用,以后可刷新

        threading.Thread(target=self._probe_engines_async, daemon=True).start()

        # 模式切换之前的代码被挪到 _probe_engines_async / _render_engine_bar 里了

        # --- 模式切换 ---
        self.mode_var = ctk.StringVar(value="single")
        mode_frame = ctk.CTkFrame(self)
        mode_frame.pack(pady=(8, 5), padx=20, fill="x")
        ctk.CTkLabel(mode_frame, text="模式:", font=("", 13, "bold")).pack(side="left", padx=(10, 5))
        ctk.CTkRadioButton(
            mode_frame, text="单张修复", variable=self.mode_var,
            value="single", command=self._switch_mode,
        ).pack(side="left", padx=5)
        ctk.CTkRadioButton(
            mode_frame, text="批量修复(整个文件夹)", variable=self.mode_var,
            value="batch", command=self._switch_mode,
        ).pack(side="left", padx=5)

        # --- 两个模式的面板(只创建,初始不打包) ---
        self.single_frame = ctk.CTkFrame(self)
        self.batch_frame = ctk.CTkFrame(self)

        # --- 装载两个模式(构建 widgets + 绑定回调到 self) ---
        mount_single_mode(self)
        mount_batch_mode(self)

        # --- 初始状态 ---
        self._switch_mode()
        self.batch_files: list[str] = []
        # 输出目录(用户自定义;None 表示用默认)
        self.single_outdir: Optional[str] = None
        self.batch_outdir: Optional[str] = None

    # ----- 工具 -----
    @staticmethod
    def _set_textbox(widget: ctk.CTkTextbox, text: str) -> None:
        """给禁用状态的 CTkTextbox 写入内容并保持禁用。"""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    @staticmethod
    def _open_dir(path: Optional[str]) -> None:
        """用系统资源管理器打开文件夹;不存在则不报错。"""
        if not path:
            return
        try:
            if os.path.isfile(path):
                # 如果给的是文件路径,打开其所在目录
                path = os.path.dirname(path)
            os.makedirs(path, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            print(f"[open dir] {e}")

    # ----- 输出目录解析 -----
    def _get_single_outdir(self, create: bool = True) -> str:
        """单张模式输出目录:用户指定优先,否则与输入文件同目录。"""
        if self.single_outdir:
            if create:
                os.makedirs(self.single_outdir, exist_ok=True)
            return self.single_outdir
        if getattr(self, "single_path", None):
            d = os.path.dirname(self.single_path) or "."
            if create:
                os.makedirs(d, exist_ok=True)
            return d
        return "."

    def _get_batch_outdir(self, create: bool = True) -> str:
        """批量模式输出目录:用户指定优先,否则 <源文件夹>/_repaired/。"""
        if self.batch_outdir:
            if create:
                os.makedirs(self.batch_outdir, exist_ok=True)
            return self.batch_outdir
        if getattr(self, "batch_dir", None):
            d = os.path.join(self.batch_dir, BATCH_SUBFOLDER)
            if create:
                os.makedirs(d, exist_ok=True)
            return d
        return BATCH_SUBFOLDER

    # ----- 模式切换 -----
    def _switch_mode(self) -> None:
        if self.mode_var.get() == "single":
            self.batch_frame.pack_forget()
            self.single_frame.pack(pady=10, padx=20, fill="x")
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(pady=10, padx=20, fill="x")

    # ----- 引擎探测(后台线程,不影响窗口弹出速度) -----
    def _probe_engines_async(self) -> None:
        """后台线程跑探测;命中缓存时几乎立即返回,不会拖慢首屏。"""
        try:
            engines = available_external_engines()
        except Exception as e:
            engines = {}
            print(f"[probe_engines] {e}")
        # Tk 不是线程安全的,必须 after(0, ...) 回到主线程改 UI
        self.after(0, self._render_engine_bar, engines)

    def _render_engine_bar(self, engines: dict[str, bool]) -> None:
        """主线程:把探测结果画到状态栏上。"""
        ok_im = engines.get("ImageMagick", False)
        ok_ff = engines.get("FFmpeg", False)
        status_text = (
            "外部引擎状态:  "
            f"ImageMagick {'✅' if ok_im else '❌(未安装)'}  "
            f"FFmpeg {'✅' if ok_ff else '❌(未安装)'}"
        )
        if ok_im and ok_ff:
            color = "lightgreen"
        elif ok_im or ok_ff:
            color = "orange"
        else:
            color = "red"
        self._engine_bar.configure(text=status_text, text_color=color)
