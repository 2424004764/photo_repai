"""修复策略包。

每个 *_strategy.py 都是一个独立的策略函数(自由函数),签名一致:
    def try_xxx(ctx: RepairContext) -> tuple[bool, str]

编排器通过 `build_default_strategy_chain(ext)` 拿到有序的 (name, fn) 列表。
新增策略只需:
    1) 新建一个 strategy.py 实现 try_xxx(ctx)
    2) 在本 __init__.py 的 build_default_strategy_chain 里加一项

【性能关键】策略模块(opencv / imagecodecs 等)需要 import cv2 / numpy 这些
原生扩展,首次 import 巨慢(冷启动 ~0.5-1s,打包后更久)。

为了**不影响窗口弹出速度**,本包顶层不做任何策略模块的 import;
`build_default_strategy_chain` 才是惰性的——首次被调用时才载入需要的策略,
缓存到模块级 dict,后续 0 开销。
"""
from __future__ import annotations

import importlib
import types
from typing import Callable

from ._context import RepairContext

__all__ = [
    "RepairContext",
    "build_default_strategy_chain",
]


# --- 惰性 import 缓存 ---
# 第一次调用 build_default_strategy_chain 时才真正 import 这些模块。
_loaded: dict[str, types.ModuleType] = {}


def _load(name: str) -> types.ModuleType:
    """惰性 import:首次访问时载入,后续直接返回缓存模块对象。"""
    mod = _loaded.get(name)
    if mod is not None:
        return mod
    mod = importlib.import_module(f".{name}", __name__)
    _loaded[name] = mod
    return mod


def build_default_strategy_chain(
    ext: str,
) -> list[tuple[str, Callable[[RepairContext], tuple[bool, str]]]]:
    """
    按 ext 返回合适的有序策略列表。

    JPEG 优先尝试字节级无损重建(保留原始熵编码,几乎不损失画质),
    然后按"宽容度从低到高"逐级尝试其他解码器。

    注:本函数是 GUI 真的点击了"修复/扫描"之后才被调用的,
    所以 cv2 / numpy / imagecodecs 的 import 成本不会拖慢启动。
    """
    chain: list[tuple[str, Callable[[RepairContext], tuple[bool, str]]]] = []

    # JPEG 文件优先尝试字节级无损重建
    jpeg_rebuild = _load("jpeg_rebuild")
    pil_mod = _load("pil")
    opencv_mod = _load("opencv")
    imagecodecs_mod = _load("imagecodecs")
    ffmpeg_mod = _load("ffmpeg")
    imagemagick_mod = _load("imagemagick")

    if ext in (".jpg", ".jpeg"):
        chain.append(("JPEG-Lossless", jpeg_rebuild.try_jpeg_rebuild))

    chain.extend([
        ("PIL-Truncated", pil_mod.try_pil),
        ("OpenCV-Multi", opencv_mod.try_opencv),
        ("OpenCV-Bytes", opencv_mod.try_opencv_bytes),
        ("imagecodecs", imagecodecs_mod.try_imagecodecs),
        ("FFmpeg", ffmpeg_mod.try_ffmpeg),
        ("ImageMagick", imagemagick_mod.try_imagemagick),
    ])
    return chain
