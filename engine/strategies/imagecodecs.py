"""imagecodecs 策略(策略 2.6):alt libjpeg 接口,有时能救 cv2/pil 都救不了的。"""
from __future__ import annotations

import os

from constants import JPEG_OPTIMIZE_PIL, JPEG_QUALITY_PIL
from ._common import save_jpeg_lossless
from ._context import RepairContext


def try_imagecodecs(ctx: RepairContext) -> tuple[bool, str]:
    try:
        import imagecodecs  # type: ignore
    except ImportError:
        return False, "imagecodecs 未安装"

    try:
        arr = imagecodecs.imread(ctx.src_path)
    except Exception as e:
        return False, f"imagecodecs.imread 失败: {type(e).__name__}: {str(e)[:100]}"

    if arr is None:
        return False, "imagecodecs 返回 None"
    try:
        size = arr.size
    except Exception:
        size = 0
    if size == 0:
        return False, "imagecodecs 返回空数组"

    try:
        import cv2  # type: ignore
        os.makedirs(ctx.output_dir, exist_ok=True)
        cv2.imwrite(
            ctx.output_path, arr,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_PIL,
             cv2.IMWRITE_JPEG_OPTIMIZE, 1 if JPEG_OPTIMIZE_PIL else 0],
        )
        return True, f"imagecodecs 解码成功 (q={JPEG_QUALITY_PIL}, shape={arr.shape})"
    except Exception:
        from PIL import Image
        mode = "RGB" if arr.ndim == 3 else "L"
        img = Image.fromarray(arr, mode=mode)
        save_jpeg_lossless(img, ctx.output_path, ctx.output_dir)
        return True, f"imagecodecs 解码成功 (q={JPEG_QUALITY_PIL}, shape={arr.shape})"
