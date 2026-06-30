"""ImageMagick 策略(策略 3):子进程调用,业界最宽容的解码器。"""
from __future__ import annotations

import os
import subprocess

from constants import JPEG_QUALITY_IMAGEMAGICK, REPAIR_TIMEOUT_SEC
from ..detection import find_imagemagick
from ._context import RepairContext


def try_imagemagick(ctx: RepairContext) -> tuple[bool, str]:
    magick = find_imagemagick()
    if not magick:
        return False, "ImageMagick 未在 PATH 中 (可选)"

    try:
        proc = subprocess.run(
            [magick, ctx.src_path, "-quality", str(JPEG_QUALITY_IMAGEMAGICK), ctx.output_path],
            capture_output=True,
            timeout=REPAIR_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, f"ImageMagick 处理超时 (>{REPAIR_TIMEOUT_SEC}s)"
    except Exception as e:
        return False, f"调用失败: {e}"

    if proc.returncode != 0:
        err = proc.stderr.decode(errors="ignore").strip()[:200]
        return False, f"退出码 {proc.returncode}: {err or '(无 stderr)'}"
    if not os.path.exists(ctx.output_path):
        return False, "ImageMagick 未生成输出文件"
    return True, "ImageMagick 转换成功"
