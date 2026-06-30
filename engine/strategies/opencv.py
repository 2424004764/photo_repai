"""OpenCV 策略(策略 2 / 2.5):多模式降级 + 字节级解码。"""
from __future__ import annotations

import os

from constants import JPEG_OPTIMIZE_PIL, JPEG_QUALITY_PIL
from ._context import RepairContext

# opencv-python-headless 是 hard dep,可以放心顶层导入;
# 若极端情况下没装,try/except ImportError 会兜底。
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _HAS_CV2 = True
except ImportError:  # pragma: no cover - 兜底分支
    cv2 = None  # type: ignore
    np = None  # type: ignore
    _HAS_CV2 = False


def try_opencv(ctx: RepairContext) -> tuple[bool, str]:
    if not _HAS_CV2:
        return False, "opencv-python 未安装"

    modes = [
        (cv2.IMREAD_UNCHANGED, "UNCHANGED"),
        (cv2.IMREAD_COLOR, "COLOR"),
        (cv2.IMREAD_REDUCED_COLOR_2, "REDUCED_2x(50%)"),
        (cv2.IMREAD_REDUCED_COLOR_4, "REDUCED_4x(25%)"),
        (cv2.IMREAD_REDUCED_COLOR_8, "REDUCED_8x(12.5%)"),
        (cv2.IMREAD_GRAYSCALE, "GRAYSCALE"),
    ]
    last = "未尝试"
    for flag, name in modes:
        img = cv2.imread(ctx.src_path, flag)
        if img is not None:
            os.makedirs(ctx.output_dir, exist_ok=True)
            ok = cv2.imwrite(
                ctx.output_path, img,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_PIL,
                 cv2.IMWRITE_JPEG_OPTIMIZE, 1 if JPEG_OPTIMIZE_PIL else 0],
            )
            if ok:
                return True, f"OpenCV 解码成功 (mode={name}, q={JPEG_QUALITY_PIL}, shape={img.shape})"
            last = f"mode={name} 解码成功但写出失败"
        else:
            last = f"mode={name} 失败"
    return False, f"所有 OpenCV 模式均失败 (最后尝试: {last})"


def try_opencv_bytes(ctx: RepairContext) -> tuple[bool, str]:
    """绕过文件系统层,直接读字节流给 cv2.imdecode,有时更宽容。"""
    if not _HAS_CV2:
        return False, "opencv-python 未安装"

    try:
        with open(ctx.src_path, "rb") as f:
            buf = np.frombuffer(f.read(), dtype=np.uint8)
        if buf.size == 0:
            return False, "文件为空"
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if img is None:
            return False, "cv2.imdecode(字节) 返回 None"
        os.makedirs(ctx.output_dir, exist_ok=True)
        cv2.imwrite(
            ctx.output_path, img,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_PIL,
             cv2.IMWRITE_JPEG_OPTIMIZE, 1 if JPEG_OPTIMIZE_PIL else 0],
        )
        return True, f"OpenCV 字节级解码成功 (q={JPEG_QUALITY_PIL}, shape={img.shape})"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"
