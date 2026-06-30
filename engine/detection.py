"""外部解码器探测(ImageMagick / FFmpeg)。

原 main.py 里 _find_imagemagick 和 _find_ffmpeg 结构几乎一样:
1. 遍历候选可执行名 → shutil.which
2. 运行 <path> --version 或 -version
3. 在输出里找特征字符串
4. 返回第一个匹配 / None

合并成一个通用函数 find_external_tool,各工具只填参数。

注意 Windows 的 system32/convert.exe 是 FAT→NTFS 工具,不是 ImageMagick,
必须 --version 自报家门才能区分,所以探测逻辑不能只看 which。
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from constants import PROBE_TIMEOUT_SEC


def find_external_tool(
    candidates: tuple[str, ...],
    version_flag: str,
    sentinel: str,
    timeout: float = PROBE_TIMEOUT_SEC,
) -> Optional[str]:
    """在候选可执行名中找第一个真正可用的外部工具。

    Args:
        candidates: 候选可执行文件名,如 ("magick", "convert")
        version_flag: 版本探测参数,如 "--version" 或 "-version"
        sentinel: 输出中必须包含的特征字符串,如 "ImageMagick" 或 "ffmpeg"
        timeout: 单次探测超时秒数

    Returns:
        工具的绝对路径;都不行则返回 None
    """
    for name in candidates:
        p = shutil.which(name)
        if not p:
            continue
        try:
            proc = subprocess.run(
                [p, version_flag],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            # 同时查 stdout 和 stderr(ImageMagick 的某些版本走 stderr)
            if sentinel in (proc.stdout + proc.stderr):
                return p
            # 部分工具的特征字符串只在 stdout 里(不区分大小写)
            if sentinel.lower() in proc.stdout.lower():
                return p
        except Exception:
            continue
    return None


# 各工具的探测参数(集中在此,方便扩展)
_IMAGEMAGICK_CANDIDATES = ("magick", "magick.exe", "convert", "convert.exe")
_FFMPEG_CANDIDATES = ("ffmpeg", "ffmpeg.exe")


def find_imagemagick() -> Optional[str]:
    """探测 ImageMagick(注意区分 Windows 系统自带的 convert.exe)。"""
    return find_external_tool(
        candidates=_IMAGEMAGICK_CANDIDATES,
        version_flag="--version",
        sentinel="ImageMagick",
    )


def find_ffmpeg() -> Optional[str]:
    """探测 FFmpeg。"""
    return find_external_tool(
        candidates=_FFMPEG_CANDIDATES,
        version_flag="-version",
        sentinel="ffmpeg",
    )


def available_external_engines() -> dict[str, bool]:
    """供 GUI 状态栏用:本机装了哪些外部引擎。"""
    return {
        "ImageMagick": bool(find_imagemagick()),
        "FFmpeg": bool(find_ffmpeg()),
    }
