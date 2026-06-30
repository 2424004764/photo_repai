"""修复策略包。

每个 *_strategy.py 都是一个独立的策略函数(自由函数),签名一致:
    def try_xxx(ctx: RepairContext) -> tuple[bool, str]

编排器通过 `build_default_strategy_chain(ext)` 拿到有序的 (name, fn) 列表。
新增策略只需:
    1) 新建一个 strategy.py 实现 try_xxx(ctx)
    2) 在本 __init__.py 的 build_default_strategy_chain 里加一项
"""
from __future__ import annotations

from typing import Callable

from ._context import RepairContext
from . import ffmpeg, imagecodecs, imagemagick, jpeg_rebuild, opencv, pil

__all__ = [
    "RepairContext",
    "build_default_strategy_chain",
]


def build_default_strategy_chain(
    ext: str,
) -> list[tuple[str, Callable[[RepairContext], tuple[bool, str]]]]:
    """按 ext 返回合适的有序策略列表。

    JPEG 优先尝试字节级无损重建(保留原始熵编码,几乎不损失画质),
    然后按"宽容度从低到高"逐级尝试其他解码器。
    """
    chain: list[tuple[str, Callable[[RepairContext], tuple[bool, str]]]] = []

    # JPEG 文件优先尝试字节级无损重建
    if ext in (".jpg", ".jpeg"):
        chain.append(("JPEG-Lossless", jpeg_rebuild.try_jpeg_rebuild))

    chain.extend([
        ("PIL-Truncated", pil.try_pil),
        ("OpenCV-Multi", opencv.try_opencv),
        ("OpenCV-Bytes", opencv.try_opencv_bytes),
        ("imagecodecs", imagecodecs.try_imagecodecs),
        ("FFmpeg", ffmpeg.try_ffmpeg),
        ("ImageMagick", imagemagick.try_imagemagick),
    ])
    return chain
