"""PIL 策略(策略 1):利用 LOAD_TRUNCATED_IMAGES 容忍截断文件。

两轮解码:
1. Image.open().load() 直接吃
2. ImageFile.Parser() 渐进喂字节
"""
from __future__ import annotations

from PIL import Image, ImageFile

from constants import PARSER_CHUNK_BYTES
from ._common import extract_exif, save_jpeg_lossless
from ._context import RepairContext


def try_pil(ctx: RepairContext) -> tuple[bool, str]:
    exif = extract_exif(ctx.src_path)
    try:
        with open(ctx.src_path, "rb") as f:
            img = Image.open(f)
            img.load()
        note = save_jpeg_lossless(img, ctx.output_path, ctx.output_dir, source_exif=exif)
        return True, f"PIL 截断容忍解码成功,{note}"
    except Exception as e1:
        try:
            parser = ImageFile.Parser()
            with open(ctx.src_path, "rb") as f:
                while True:
                    chunk = f.read(PARSER_CHUNK_BYTES)
                    if not chunk:
                        break
                    parser.feed(chunk)
            img = parser.close()
            if img is None:
                return False, f"PIL Parser 无法解析 (第一轮错误: {type(e1).__name__})"
            note = save_jpeg_lossless(img, ctx.output_path, ctx.output_dir, source_exif=exif)
            return True, f"PIL Parser 渐进解析成功,{note}"
        except Exception as e2:
            return False, (
                f"两轮 PIL 解码均失败: "
                f"第一轮 {type(e1).__name__}; "
                f"第二轮 {type(e2).__name__}: {str(e2)[:80]}"
            )
