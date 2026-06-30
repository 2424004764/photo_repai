# -*- coding: utf-8 -*-
"""
AI & 传统图片修复工具 v2.0

多策略级联修复引擎 —— 按"宽容度从低到高"逐级尝试:
    1) PIL + LOAD_TRUNCATED_IMAGES  —— 截断文件
    2) OpenCV cv2.imread            —— 头/段损坏
    3) ImageMagick 子进程           —— 任意结构损坏 (PATH 中须有 magick/convert)
    4) JPEG 段级重建                —— 最后的字节级挽救 (仅 .jpg/.jpeg)

支持单张修复与批量修复两种模式。
"""
from __future__ import annotations

from PIL import Image, ImageFile

# === 关键:让 PIL 容忍截断文件 ===
ImageFile.LOAD_TRUNCATED_IMAGES = True
# 不限制像素数,避免超大图触发 DecompressionBombWarning
Image.MAX_IMAGE_PIXELS = None

from gui import ImageRepairApp  # noqa: E402  (import after PIL config)


if __name__ == "__main__":
    app = ImageRepairApp()
    app.mainloop()
