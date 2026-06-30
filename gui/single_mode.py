"""单张修复模式:widgets + 3 个回调。

mount_single_mode(app) 在 app.single_frame 上构建面板,
并把 _pick_single / _pick_single_outdir / _repair_single 绑定到 app 实例上,
保持原有的 self.* 访问语义。
"""
from __future__ import annotations

import os
import types
from tkinter import filedialog

import customtkinter as ctk

from constants import QUALITY_WARN_RATIO_HIGH, QUALITY_WARN_RATIO_LOW
from engine import ImageRepairer


def mount_single_mode(app: ctk.CTk) -> None:
    """构建单张模式面板,并把回调方法绑定到 app 实例。"""

    def _pick_single(self: ctk.CTk) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Image files", " ".join(f"*{e}" for e in self.SUPPORTED_EXTS))]
        )
        if path:
            self.single_path = path
            self.single_path_lbl.configure(text=os.path.basename(path), text_color="white")
            self._set_textbox(self.single_status, "已选择文件,点击下方按钮开始修复")

    def _pick_single_outdir(self: ctk.CTk) -> None:
        initial = self.single_outdir or (
            os.path.dirname(self.single_path) if getattr(self, "single_path", None) else os.getcwd()
        )
        d = filedialog.askdirectory(
            title="选择单张修复输出目录", initialdir=initial,
        )
        if d:
            self.single_outdir = d
            self.single_outdir_lbl.configure(text=f"输出: {d}", text_color="white")
            self.single_outdir_btn.configure(state="normal")

    def _repair_single(self: ctk.CTk) -> None:
        if not getattr(self, "single_path", None):
            self._set_textbox(self.single_status, "❌ 请先选择文件!")
            return
        self._set_textbox(self.single_status, "⏳ 正在尝试多策略修复...\n")
        self.update()

        out_dir = self._get_single_outdir(create=True)
        repairer = ImageRepairer(self.single_path, output_dir=out_dir)
        result = repairer.repair()

        if result.success:
            # 文件大小对比 —— 直观显示画质保留情况
            try:
                src_size = os.path.getsize(self.single_path)
                out_size = os.path.getsize(result.output_path)
                ratio = out_size / src_size * 100
                size_info = (
                    f"原文件: {src_size/1024:.1f} KB  →  "
                    f"修复后: {out_size/1024:.1f} KB  ({ratio:.0f}%)\n"
                )
                if ratio < QUALITY_WARN_RATIO_LOW:
                    size_info += (
                        "⚠️ 文件明显变小,可能存在画质损失。"
                        "若引擎是 Lossless:这是异常,请反馈。\n"
                    )
                elif ratio >= QUALITY_WARN_RATIO_HIGH:
                    size_info += "✅ 文件大小近原始(高质量保留)\n"
            except Exception:
                size_info = ""
            text = (
                f"✅ 修复成功!\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"使用引擎: {result.strategy}\n"
                f"{size_info}"
                f"输出文件: {result.output_path}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"尝试过程:\n" + "\n".join(result.attempts)
            )
            self._set_textbox(self.single_status, text)
            self.single_outdir_btn.configure(state="normal")
        else:
            missing = []
            for line in result.attempts:
                if "未在 PATH 中" in line or "未安装" in line:
                    missing.append(line)
            hint = ""
            if missing:
                hint = (
                    "\n\n💡 安装提示:\n"
                    "  • ImageMagick (成功率最高):\n"
                    "      choco install imagemagick\n"
                    "      或访问 https://imagemagick.org\n"
                    "  • FFmpeg (很多视频用户已有):\n"
                    "      choco install ffmpeg\n"
                    "      或访问 https://ffmpeg.org\n"
                    "  装完后重启本程序即可自动启用"
                )
            text = (
                f"❌ 所有修复引擎均失败\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"尝试过程:\n" + "\n".join(result.attempts)
                + hint
            )
            self._set_textbox(self.single_status, text)

    # --- 把回调绑到 app 实例 (必须在 widgets 构建之前,因为 widgets 引用 command=app._xxx) ---
    app._pick_single = types.MethodType(_pick_single, app)
    app._pick_single_outdir = types.MethodType(_pick_single_outdir, app)
    app._repair_single = types.MethodType(_repair_single, app)

    # --- 构建 widgets ---
    ctk.CTkButton(
        app.single_frame, text="选择损坏图片", command=app._pick_single,
    ).pack(pady=(10, 5), padx=10)
    app.single_path_lbl = ctk.CTkLabel(
        app.single_frame, text="未选择任何文件", text_color="gray",
    )
    app.single_path_lbl.pack(pady=2)

    # 输出目录行
    out_row1 = ctk.CTkFrame(app.single_frame, fg_color="transparent")
    out_row1.pack(pady=8, padx=10, fill="x")
    ctk.CTkButton(
        out_row1, text="选择输出目录", width=140, command=app._pick_single_outdir,
    ).pack(side="left", padx=(0, 6))
    app.single_outdir_btn = ctk.CTkButton(
        out_row1, text="📂 打开输出文件夹", width=160,
        fg_color="gray", hover_color="#555555", state="disabled",
        command=lambda: app._open_dir(app._get_single_outdir(create=False)),
    )
    app.single_outdir_btn.pack(side="left")
    app.single_outdir_lbl = ctk.CTkLabel(
        app.single_frame, text="输出: 默认(与输入文件同目录)", text_color="gray", font=("", 11),
    )
    app.single_outdir_lbl.pack(pady=(2, 4))

    ctk.CTkButton(
        app.single_frame, text="一键尝试修复",
        fg_color="green", hover_color="#006400",
        command=app._repair_single,
    ).pack(pady=10)
    # 状态用文本框,完整显示每个引擎的尝试结果
    app.single_status = ctk.CTkTextbox(app.single_frame, height=170, wrap="word")
    app.single_status.pack(pady=5, padx=10, fill="x")
    app.single_status.configure(state="disabled")
    app._set_textbox(app.single_status, "等待选择文件...")
