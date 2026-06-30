"""批量修复模式:widgets + 5 个回调(含后台 worker 线程)。

mount_batch_mode(app) 在 app.batch_frame 上构建面板,
并把 _pick_batch_dir / _pick_batch_outdir / _scan_batch / _start_batch_repair / _batch_worker 绑定到 app。
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
import time
import types
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from engine import ImageRepairer, classify_image
from engine.strategies._common import is_image_clean


def mount_batch_mode(app: ctk.CTk) -> None:
    """构建批量模式面板,并把回调方法绑定到 app 实例。"""

    def _pick_batch_dir(self: ctk.CTk) -> None:
        d = filedialog.askdirectory()
        if d:
            self.batch_dir = d
            self.batch_dir_lbl.configure(text=d, text_color="white")

    def _pick_batch_outdir(self: ctk.CTk) -> None:
        initial = self.batch_outdir or (
            self.batch_dir if getattr(self, "batch_dir", None) else os.getcwd()
        )
        d = filedialog.askdirectory(
            title="选择批量修复输出目录", initialdir=initial,
        )
        if d:
            self.batch_outdir = d
            self.batch_outdir_lbl.configure(text=f"输出: {d}", text_color="white")
            self.batch_outdir_btn.configure(state="normal")

    def _scan_batch(self: ctk.CTk) -> None:
        """扫描文件夹,逐条把文件塞进 listbox(带动画感)。

        实现:后台 worker 走 os.walk + is_image_clean,
        把每条结果 put 到 queue;主线程 after 轮询 get,
        每 30ms 插入一行,更新状态栏。"""
        d = getattr(self, "batch_dir", None)
        if not d:
            self.batch_status.configure(text="请先选择文件夹!", text_color="red")
            return

        # 重置 listbox 和行号映射
        self.batch_file_lines = [None]  # 行 0 = 标题(暂未写入)
        self.batch_files = []           # 最终的完整文件列表
        self._scan_good_cnt = 0
        self._scan_bad_cnt = 0

        self.batch_listbox.configure(state="normal")
        self.batch_listbox.delete("1.0", "end")
        self.batch_listbox.insert("end", "扫描中...\n")
        self.batch_listbox.configure(state="disabled")  # 中间不允许编辑
        self.batch_status.configure(text="扫描中...", text_color="yellow")

        scan_queue: queue.Queue = queue.Queue()
        STOP = object()  # 哨兵

        def worker() -> None:
            """后台线程:走目录 + is_image_clean + 限速 put。"""
            try:
                for root, _, names in os.walk(d):
                    for n in names:
                        if n.lower().endswith(self.SUPPORTED_EXTS):
                            fp = os.path.join(root, n)
                            rel = os.path.relpath(fp, d)
                            icon = "✓" if is_image_clean(fp) else "⚠"
                            scan_queue.put((fp, rel, icon))
                            time.sleep(0.03)  # 限速 30ms/条,让动画可见
            finally:
                scan_queue.put(STOP)

        def poll() -> None:
            """主线程:从 queue 拉一条塞进 listbox,直到收到 STOP。"""
            try:
                item = scan_queue.get_nowait()
            except queue.Empty:
                self.after(20, poll)
                return

            if item is STOP:
                # 收尾
                total = len(self.batch_file_lines) - 1
                # 把"扫描中..."那行替换成统计行
                self.batch_listbox.configure(state="normal")
                self.batch_listbox.delete("1.0", "2.0")
                if total == 0:
                    self.batch_listbox.insert("1.0", "未发现支持的图片文件\n")
                    self.batch_status.configure(text="扫描完成:无文件", text_color="white")
                else:
                    self.batch_listbox.insert(
                        "1.0",
                        f"共 {total} 个文件(✓ 好 {self._scan_good_cnt} 个 / "
                        f"⚠ 可能损坏 {self._scan_bad_cnt} 个):\n",
                    )
                    self.batch_status.configure(
                        text=f"扫描完成:{total} 个文件(✓{self._scan_good_cnt} / "
                             f"⚠{self._scan_bad_cnt}) - 双击文件查看详细诊断",
                        text_color="white",
                    )
                self.batch_listbox.configure(state="disabled")
                return

            fp, rel, icon = item
            self.batch_file_lines.append(fp)
            self.batch_files.append(fp)
            if icon == "✓":
                self._scan_good_cnt += 1
            else:
                self._scan_bad_cnt += 1
            # 追加这一行(可见的"逐条出现"效果)
            self.batch_listbox.configure(state="normal")
            self.batch_listbox.insert("end", f"  {icon} {rel}\n")
            # 实时更新状态栏进度
            shown = len(self.batch_file_lines) - 1
            self.batch_status.configure(
                text=f"扫描中:已发现 {shown} 个(✓{self._scan_good_cnt} / "
                     f"⚠{self._scan_bad_cnt})...",
                text_color="yellow",
            )
            self.batch_listbox.configure(state="disabled")
            # 继续轮询
            self.after(10, poll)

        # 启动 worker + 主线程轮询
        threading.Thread(target=worker, daemon=True).start()
        self.after(20, poll)

    def _start_batch_repair(self: ctk.CTk) -> None:
        if not self.batch_files:
            self.batch_status.configure(text="请先扫描文件夹!", text_color="red")
            return
        # 后台线程避免阻塞 GUI
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def _show_file_diagnostic(self: ctk.CTk, file_path: str) -> None:
        """弹窗显示某文件的完整三态诊断(state / strategy / message / 全部级联尝试日志)。"""
        from engine.classifier import ImageClassification  # 局部导入,避免循环

        win = ctk.CTkToplevel(self)
        win.title(f"诊断 - {os.path.basename(file_path)}")
        win.geometry("640x520")
        # 模态;若已有其他 grab,会抛 TclError,降级为非模态
        try:
            win.grab_set()
        except Exception:
            pass

        # 文件名 + 完整路径
        ctk.CTkLabel(
            win, text=os.path.basename(file_path),
            font=("", 15, "bold"),
        ).pack(pady=(15, 2), padx=20)
        ctk.CTkLabel(
            win, text=file_path, text_color="gray",
            font=("", 11), wraplength=600,
        ).pack(pady=(0, 10), padx=20)

        # 状态大字(诊断过程中显示"诊断中...")
        status_lbl = ctk.CTkLabel(
            win, text="⏳ 诊断中...",
            font=("", 16, "bold"), text_color="gray",
        )
        status_lbl.pack(pady=8)
        detail_lbl = ctk.CTkLabel(
            win, text="", wraplength=600, justify="left", font=("", 11),
        )
        detail_lbl.pack(pady=5, padx=20)

        # 关闭按钮(诊断过程中就允许关)
        ctk.CTkButton(win, text="关闭", command=win.destroy).pack(pady=10)

        # 线程间通信:worker 线程把结果 put 到 queue,主线程 after 轮询 get
        # (tkinter 任何 API 都必须在主线程调,所以 worker 不能用 after)
        result_queue: queue.Queue = queue.Queue()

        def worker() -> None:
            c = classify_image(file_path)
            result_queue.put(c)

        def _populate_ui(c: ImageClassification) -> None:
            state_text, state_color = {
                "clean":        ("✓ 好图(无需修复)", "lightgreen"),
                "repairable":   (f"⚠ 可修复(策略: {c.strategy})", "orange"),
                "unrepairable": ("✗ 救不了", "red"),
            }[c.state]
            status_lbl.configure(text=state_text, text_color=state_color)
            if c.message:
                detail_lbl.configure(text=c.message)
            if c.attempts:
                lf = ctk.CTkFrame(win)
                lf.pack(pady=(8, 0), padx=20, fill="both", expand=True)
                ctk.CTkLabel(
                    lf, text=f"级联尝试日志(共 {len(c.attempts)} 步):",
                    font=("", 12, "bold"),
                ).pack(anchor="w", padx=4, pady=(4, 0))
                box = ctk.CTkTextbox(lf, height=180, wrap="word")
                box.pack(padx=4, pady=4, fill="both", expand=True)
                box.insert("1.0", "\n".join(c.attempts))
                box.configure(state="disabled")

        def poll() -> None:
            try:
                c = result_queue.get_nowait()
                _populate_ui(c)
            except queue.Empty:
                win.after(100, poll)

        # 主线程起轮询,worker 线程开跑
        win.after(100, poll)
        threading.Thread(target=worker, daemon=True).start()

    def _batch_worker(self: ctk.CTk) -> None:
        total = len(self.batch_files)
        ok_cnt = fail_cnt = copied_cnt = 0
        fail_files: list[str] = []
        total_src_size = 0
        total_out_size = 0
        out_dir = self._get_batch_outdir(create=True)
        # 读取 checkbox 状态(只在 worker 启动时读一次,避免运行中切换导致不一致)
        copy_unchanged = bool(self.batch_copy_unchanged_var.get())

        for idx, path in enumerate(self.batch_files, 1):
            base = os.path.basename(path)
            self.after(0, lambda i=idx, t=total, p=base: (
                self.batch_status.configure(
                    text=f"[{i}/{t}] 处理中: {p}", text_color="yellow"
                )
            ))

            # ★ 选项开启时:PIL 严格模式能开的图,直接复制原文件,不跑级联
            if copy_unchanged and is_image_clean(path):
                try:
                    dst = os.path.join(out_dir, base)
                    # 若目标已存在(用户多次跑),避免覆盖;改名加 _orig
                    if os.path.exists(dst):
                        stem, ext = os.path.splitext(base)
                        dst = os.path.join(out_dir, f"{stem}_orig{ext}")
                    shutil.copy2(path, dst)
                    copied_cnt += 1
                    self.after(0, lambda v=idx / total: self.batch_progress.set(v))
                    continue
                except Exception:
                    # 复制失败就退化走级联,不放弃
                    pass

            try:
                result = ImageRepairer(path, output_dir=out_dir).repair()
                if result.success:
                    ok_cnt += 1
                    try:
                        total_src_size += os.path.getsize(path)
                        total_out_size += os.path.getsize(result.output_path)
                    except OSError:
                        pass
                else:
                    fail_cnt += 1
                    fail_files.append(base)
            except Exception:
                fail_cnt += 1
                fail_files.append(base)

            progress = idx / total
            self.after(0, lambda v=progress: self.batch_progress.set(v))

        # 总体大小对比
        if total_src_size > 0:
            ratio = total_out_size / total_src_size * 100
            size_info = (
                f"总体大小: {total_src_size/1024:.0f} KB → {total_out_size/1024:.0f} KB ({ratio:.0f}%)\n"
            )
        else:
            size_info = ""

        summary_parts = [f"批量完成 ✅ 成功 {ok_cnt} / 失败 {fail_cnt} / 总 {total}"]
        if copied_cnt > 0:
            summary_parts.append(f"  其中原样复制 {copied_cnt} 张")
        summary = "\n".join(summary_parts) + f"\n{size_info}输出目录: {out_dir}"
        if fail_files:
            summary += f"\n失败文件(前 5 个): {', '.join(fail_files[:5])}"
        all_good = fail_cnt == 0
        color = "green" if all_good else ("orange" if (ok_cnt + copied_cnt) > 0 else "red")
        self.after(0, lambda: (
            self.batch_status.configure(text=summary, text_color=color),
            self.batch_outdir_btn.configure(state="normal"),
        ))

    # --- 把回调绑到 app 实例 (必须在 widgets 构建之前,因为 widgets 引用 command=app._xxx) ---
    app._pick_batch_dir = types.MethodType(_pick_batch_dir, app)
    app._pick_batch_outdir = types.MethodType(_pick_batch_outdir, app)
    app._scan_batch = types.MethodType(_scan_batch, app)
    app._start_batch_repair = types.MethodType(_start_batch_repair, app)
    app._batch_worker = types.MethodType(_batch_worker, app)
    app._show_file_diagnostic = types.MethodType(_show_file_diagnostic, app)

    # --- 构建 widgets ---
    ctk.CTkButton(
        app.batch_frame, text="选择文件夹", command=app._pick_batch_dir,
    ).pack(pady=(10, 5), padx=10)
    app.batch_dir_lbl = ctk.CTkLabel(
        app.batch_frame, text="未选择文件夹", text_color="gray",
    )
    app.batch_dir_lbl.pack(pady=2)

    # 输出目录行
    out_row2 = ctk.CTkFrame(app.batch_frame, fg_color="transparent")
    out_row2.pack(pady=8, padx=10, fill="x")
    ctk.CTkButton(
        out_row2, text="选择输出目录", width=140, command=app._pick_batch_outdir,
    ).pack(side="left", padx=(0, 6))
    app.batch_outdir_btn = ctk.CTkButton(
        out_row2, text="📂 打开输出文件夹", width=160,
        fg_color="gray", hover_color="#555555", state="disabled",
        command=lambda: app._open_dir(app._get_batch_outdir(create=False)),
    )
    app.batch_outdir_btn.pack(side="left")
    app.batch_outdir_lbl = ctk.CTkLabel(
        app.batch_frame, text="输出: 默认(<源文件夹>/_repaired/)", text_color="gray", font=("", 11),
    )
    app.batch_outdir_lbl.pack(pady=(2, 4))

    ctk.CTkButton(
        app.batch_frame, text="扫描可修复的图片",
        command=app._scan_batch,
    ).pack(pady=8)
    app.batch_listbox = ctk.CTkTextbox(app.batch_frame, height=110)
    app.batch_listbox.pack(pady=5, padx=10, fill="x")
    # 用 state="normal" 让双击事件能触发,但绑 <Key> 阻止编辑;
    # state="disabled" 会屏蔽鼠标事件(包括双击)
    app.batch_listbox.configure(state="normal")
    # CTkTextbox 的 bind() 是 no-op,所有事件都得绑到内部 _textbox
    inner_text = app.batch_listbox._textbox
    inner_text.bind("<Key>", lambda e: "break")  # 阻止键盘编辑

    # ★ 双击文件行 → 弹窗显示详细诊断
    def _on_listbox_double_click(event) -> None:
        try:
            index = inner_text.index(f"@{event.x},{event.y}")
            line_num = int(index.split(".")[0]) - 1  # 0-based
            file_map = getattr(app, "batch_file_lines", None)
            if file_map and 0 <= line_num < len(file_map) and file_map[line_num]:
                app._show_file_diagnostic(file_map[line_num])
        except Exception as e:
            print(f"[diagnostic click] {e}")
    inner_text.bind("<Double-Button-1>", _on_listbox_double_click)
    app.batch_progress = ctk.CTkProgressBar(app.batch_frame)
    app.batch_progress.set(0)
    app.batch_progress.pack(pady=8, padx=10, fill="x")
    # ★ 新增:把无需修复的好图片也复制到输出目录
    app.batch_copy_unchanged_var = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(
        app.batch_frame,
        text="把无需修复的好图片也复制到输出目录",
        variable=app.batch_copy_unchanged_var,
    ).pack(pady=(0, 8))
    ctk.CTkButton(
        app.batch_frame, text="开始批量修复",
        fg_color="green", hover_color="#006400",
        command=app._start_batch_repair,
    ).pack(pady=8)
    app.batch_status = ctk.CTkLabel(
        app.batch_frame, text="", text_color="gray", justify="left",
    )
    app.batch_status.pack(pady=5, padx=10)
