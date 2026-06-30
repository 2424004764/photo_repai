# -*- coding: utf-8 -*-
"""
一键打包脚本 —— 调 PyInstaller + build.spec。

用法:
    uv run python build.py            # 默认:清理后打包
    uv run python build.py --keep     # 保留上次的 build/ dist/
    uv run python build.py --onefile  # 单文件模式(慢点启动,易分享)
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "build.spec"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def _clean() -> None:
    """清理上次构建产物。"""
    for d in (BUILD, DIST):
        if d.exists():
            print(f"  🧹 清理 {d.relative_to(ROOT)}/")
            shutil.rmtree(d, ignore_errors=True)


def _run(spec: Path, onefile: bool) -> int:
    """
    调 PyInstaller。`onefile=True` 时给 spec 传 --onefile 覆盖默认 onedir。
    """
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec),
        "--noconfirm",
    ]
    if onefile:
        cmd.append("--onefile")

    print("  🚀 执行:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def _report(onefile: bool) -> Path:
    """返回最终 EXE 的绝对路径(平台相关)。"""
    name = "PhotoRepair"
    if sys.platform == "win32":
        return DIST / f"{name}.exe"
    # macOS 上 PyInstaller 会产出 .app;Linux/macOS 单文件模式就是裸二进制
    if sys.platform == "darwin":
        app = DIST / f"{name}.app"
        return app if app.exists() else DIST / name
    return DIST / name


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 photo_repair 为 EXE")
    parser.add_argument("--keep", action="store_true", help="保留 build/ dist/")
    parser.add_argument(
        "--onefile", action="store_true", help="单文件模式(默认是单文件夹)"
    )
    args = parser.parse_args()

    if not SPEC.exists():
        print(f"❌ 找不到 {SPEC}", file=sys.stderr)
        return 1

    print("📦 开始打包 photo_repair ...")
    print(f"   spec:  {SPEC}")
    print(f"   python: {sys.version.split()[0]}")
    print(f"   mode:  {'onefile' if args.onefile else 'onedir (folder)'}")

    if not args.keep:
        _clean()

    rc = _run(SPEC, args.onefile)
    if rc != 0:
        print(f"\n❌ PyInstaller 退出码 {rc}", file=sys.stderr)
        return rc

    out = _report(args.onefile)
    print("\n✅ 打包完成!")
    print(f"   产物路径: {out}")
    if (DIST).exists():
        print(f"   dist 大小: { _size_human(DIST) }")
    print("\n👉 在目标机器上首次运行前,确认已安装 ImageMagick / FFmpeg(可选):")
    print("   choco install imagemagick ffmpeg")
    return 0


def _size_human(p: Path) -> str:
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"


if __name__ == "__main__":
    sys.exit(main())
