"""多策略修复引擎的编排器(薄薄一层)。

工作流程:
1. 构造时根据 src_path 计算 output_path(<src_name>_fixed.jpg)
2. repair() 按 ext 从注册表取有序策略链,逐个尝试,第一个成功的就返回
3. 成功后可选调用 fix_truncation_placeholder 修复截断产生的占位色
"""
from __future__ import annotations

import os
from typing import Optional

from constants import OUTPUT_EXT, OUTPUT_SUFFIX
from .detection import available_external_engines
from .result import RepairResult
from .strategies import build_default_strategy_chain
from .strategies._common import fix_truncation_placeholder
from .strategies._context import RepairContext


class ImageRepairer:
    """对一个文件做多策略级联修复。"""

    def __init__(self, src_path: str, output_dir: Optional[str] = None) -> None:
        self.src_path = src_path
        self.src_name = os.path.basename(src_path)
        self.ext = os.path.splitext(src_path)[1].lower()
        self.output_dir = output_dir or os.path.dirname(src_path) or "."
        self.output_path = os.path.join(
            self.output_dir,
            f"{os.path.splitext(self.src_name)[0]}{OUTPUT_SUFFIX}{OUTPUT_EXT}",
        )
        self.ctx = RepairContext(
            src_path=self.src_path,
            output_path=self.output_path,
            output_dir=self.output_dir,
            ext=self.ext,
        )

    # --------------------------------------------------------------------- #
    #  对外主入口
    # --------------------------------------------------------------------- #
    def repair(self) -> RepairResult:
        attempts: list[str] = []
        strategies = build_default_strategy_chain(self.ext)

        for name, fn in strategies:
            try:
                ok, msg = fn(self.ctx)
            except Exception as e:
                ok, msg = False, f"{type(e).__name__}: {e}"
            attempts.append(f"[{name}] {'OK' if ok else 'FAIL'} - {msg}")
            if ok:
                # ★ 截断文件:自动修复底部占位色(若检测到)
                if fix_truncation_placeholder(self.src_path, self.output_path):
                    msg += " + 已修复底部截断占位"
                    attempts.append("[PlaceholderFix] OK - 检测到截断占位,已用上行颜色填充")
                return RepairResult(
                    success=True,
                    strategy=name,
                    message=msg,
                    output_path=self.output_path,
                    attempts=attempts,
                )

        return RepairResult(
            success=False,
            strategy="None",
            message="所有策略均失败",
            output_path=None,
            attempts=attempts,
        )

    # --------------------------------------------------------------------- #
    #  探测:本机可用的外部引擎 (供 GUI 状态栏提示用)
    # --------------------------------------------------------------------- #
    @staticmethod
    def available_external_engines() -> dict[str, bool]:
        """委托给 engine.detection,保持向后兼容。"""
        return available_external_engines()
