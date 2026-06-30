"""FFmpeg 策略(策略 3):宽容度比 libjpeg 高一档。"""
from __future__ import annotations

import os
import subprocess

from constants import JPEG_QUALITY_FFMPEG, REPAIR_TIMEOUT_SEC
from ..detection import find_ffmpeg
from ._context import RepairContext


def try_ffmpeg(ctx: RepairContext) -> tuple[bool, str]:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return False, "FFmpeg 未在 PATH 中 (可选,装了能救很多 JPEG)"

    # -q:v 1 = FFmpeg 最高 JPEG 质量; 2 = 很高 (旧默认)
    os.makedirs(ctx.output_dir, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                ffmpeg, "-y",
                "-err_detect", "ignore_err",
                "-fflags", "+discardcorrupt",
                "-i", ctx.src_path,
                "-q:v", str(JPEG_QUALITY_FFMPEG),  # 最高质量 (1=best, 2=high)
                "-frames:v", "1",                  # 只要一帧 (静态图)
                ctx.output_path,
            ],
            capture_output=True,
            timeout=REPAIR_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg 处理超时 (>{REPAIR_TIMEOUT_SEC}s)"
    except Exception as e:
        return False, f"FFmpeg 调用失败: {e}"

    if os.path.exists(ctx.output_path) and os.path.getsize(ctx.output_path) > 0:
        return True, f"FFmpeg 宽容解码成功 (q:v={JPEG_QUALITY_FFMPEG} 最高质量)"
    err = proc.stderr.decode(errors="ignore").strip().splitlines()[-3:]
    return False, f"FFmpeg 退出码 {proc.returncode}: {' | '.join(err)[:200]}"
