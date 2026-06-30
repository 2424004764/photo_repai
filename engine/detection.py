"""外部解码器探测(ImageMagick / FFmpeg)。

原 main.py 里 _find_imagemagick 和 _find_ffmpeg 结构几乎一样:
1. 遍历候选可执行名 → shutil.which
2. 运行 <path> --version 或 -version
3. 在输出里找特征字符串
4. 返回第一个匹配 / None

合并成一个通用函数 find_external_tool,各工具只填参数。

注意 Windows 的 system32/convert.exe 是 FAT→NTFS 工具,不是 ImageMagick,
必须 --version 自报家门才能区分,所以探测逻辑不能只看 which。

【性能关键】所有探测都进 JSON 缓存(用户配置目录):
- 没装过的工具 → 缓存 24h 不重探,避免冷启动撞到 system32/convert.exe 等
  "可执行但又不是 ImageMagick"的命令,白白等超时
- 装过的工具 → 也缓存,但只在一次 session 内用;若担心,传 force_refresh=True 重探
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from constants import (
    APP_USER_DIR_NAME,
    PROBE_CACHE_FILENAME,
    PROBE_CACHE_TTL_HOURS,
    PROBE_TIMEOUT_SEC,
)


# ---------- 缓存 IO ----------

def _user_config_dir() -> Path:
    """跨平台的用户配置目录。失败兜底用家目录。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_USER_DIR_NAME


def _cache_path() -> Path:
    return _user_config_dir() / PROBE_CACHE_FILENAME


def _load_cache() -> dict:
    """读缓存;不存在 / 格式坏 / TTL 过期 → 返回空 dict(代表"全部待探测")。"""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    # 兼容旧格式(纯 {name: bool});新格式带 timestamp
    if all(isinstance(v, bool) for v in data.values()):
        return data
    # 凭 timestamp 判断 TTL
    now = time.time()
    ttl = PROBE_CACHE_TTL_HOURS * 3600
    fresh: dict[str, bool] = {}
    for name, payload in data.items():
        if not isinstance(payload, dict):
            continue
        ts = payload.get("ts", 0)
        avail = payload.get("available")
        if isinstance(avail, bool) and (now - ts) < ttl:
            fresh[name] = avail
    return fresh


def _save_cache(avail: dict[str, bool]) -> None:
    """持久化探测结果,带时间戳。失败静默(非阻塞探测路径)。"""
    try:
        d = _user_config_dir()
        d.mkdir(parents=True, exist_ok=True)
        payload = {name: {"available": v, "ts": time.time()} for name, v in avail.items()}
        _cache_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ---------- 探测 ----------

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
        timeout: 单次探测超时秒数(默认常量,这里缩到 1.5s)

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
                # 部分工具(Windows ffmpeg 等)输出不是 UTF-8,用系统默认避免
                # UnicodeDecodeError 把线程打挂。
                errors="replace",
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


def available_external_engines(*, force_refresh: bool = False) -> dict[str, bool]:
    """供 GUI 状态栏用:本机装了哪些外部引擎。

    命中持久化缓存时**完全不调 subprocess**,进程秒起。
    缓存键:ImageMagick / FFmpeg。

    Args:
        force_refresh: True 时强制重新探测并覆盖缓存(供设置页/调试用)。
    """
    cached = {} if force_refresh else _load_cache()

    def _have(name: str) -> Optional[bool]:
        return cached.get(name)

    engines: dict[str, bool] = {}
    need_probe: list[str] = []

    # 先用缓存填空,缺啥探啥
    for name, finder in (
        ("ImageMagick", find_imagemagick),
        ("FFmpeg", find_ffmpeg),
    ):
        hit = _have(name)
        if hit is None:
            need_probe.append(name)
        else:
            engines[name] = hit

    # 真要探测的工具(最多两个)
    if need_probe:
        for name in need_probe:
            finder = find_imagemagick if name == "ImageMagick" else find_ffmpeg
            engines[name] = bool(finder())
        # 写缓存(包含本次新填的 + 已有缓存的)
        to_save = {**cached, **engines}
        _save_cache(to_save)

    return engines
