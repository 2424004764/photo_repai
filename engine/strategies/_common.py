"""多个策略共用的辅助函数。

原本散落在 ImageRepairer 上的:
- save_jpeg_lossless  (PIL 写出,最高质量 + 优化 + 保留 EXIF)
- extract_exif       (从原图提取 EXIF 字节)
- is_input_truncated (看文件末尾是否有 EOI 标记)
- fix_truncation_placeholder (修复截断文件产生的灰色/绿色占位)

全部抽成自由函数,签名由 self.* 改为显式入参。
"""
from __future__ import annotations

import os
from typing import Optional

from PIL import Image, ImageFile

from constants import (
    EOI_SCAN_TAIL_BYTES,
    JPEG_OPTIMIZE_PIL,
    JPEG_PROGRESSIVE_PIL,
    JPEG_QUALITY_PIL,
    PARSER_CHUNK_BYTES,
    PLACEHOLDER_HALF_SCAN,
    PLACEHOLDER_MIN_HEIGHT,
    PLACEHOLDER_ROW_STD_THRESHOLD,
)

# === 关键:让 PIL 容忍截断文件 ===
# 这里也设置一次,因为 PIL 解析行为依赖这个开关,任何使用 PIL 的策略都受益。
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None


def save_jpeg_lossless(
    img: Image.Image,
    output_path: str,
    output_dir: str,
    source_exif: Optional[bytes] = None,
) -> str:
    """PIL 写出 JPEG,质量最高 + 优化 Huffman + 保留 EXIF。"""
    os.makedirs(output_dir, exist_ok=True)
    save_kwargs = {
        "quality": JPEG_QUALITY_PIL,
        "optimize": JPEG_OPTIMIZE_PIL,
        "progressive": JPEG_PROGRESSIVE_PIL,
    }
    if source_exif:
        save_kwargs["exif"] = source_exif
    img.convert("RGB").save(output_path, "JPEG", **save_kwargs)
    return f"已用 quality={JPEG_QUALITY_PIL} + optimize 保存"


def extract_exif(src_path: str) -> Optional[bytes]:
    """从原图提取 EXIF,便于修复后保留。"""
    try:
        with Image.open(src_path) as im:
            exif = im.info.get("exif")
            return exif if isinstance(exif, bytes) else None
    except Exception:
        return None


def is_image_clean(src_path: str) -> bool:
    """用 PIL 严格模式打开,验证图是否本来就完好(无需任何修复)。

    实现细节:这里临时关闭 LOAD_TRUNCATED_IMAGES 容忍开关,任何错误都视为损坏。
    否则在 LOAD_TRUNCATED_IMAGES=True 下,PIL 会容忍 95% 的截断,
    导致"明显损坏"的图也被判 clean,影响批量模式的好图片复制逻辑。
    """
    saved = ImageFile.LOAD_TRUNCATED_IMAGES
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        with Image.open(src_path) as im:
            im.load()
            im.verify()  # 再做一次完整性校验
        return True
    except Exception:
        return False
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = saved


def is_input_truncated(src_path: str) -> bool:
    """检测原图是否被截断(无 FFD9 EOI 结尾)。"""
    try:
        with open(src_path, "rb") as f:
            tail = f.read()[-EOI_SCAN_TAIL_BYTES:]
        return not tail.endswith(b"\xff\xd9")
    except Exception:
        return False


def fix_truncation_placeholder(src_path: str, output_path: str) -> bool:
    """若原图被截断,解码器会用默认 DC 值填充缺失的 MCU,产生灰色/绿色占位。
    从底部向上扫描找最后一行有效内容,将其颜色向下延伸覆盖占位区。
    """
    if not is_input_truncated(src_path):
        return False
    if not os.path.exists(output_path):
        return False

    try:
        import numpy as np

        img = Image.open(output_path).convert("RGB")
        arr = np.array(img)
        h, w, _ = arr.shape
        if h < PLACEHOLDER_MIN_HEIGHT:
            return False

        # 从底部向上扫描,找第一行方差 > 阈值 (即有真实内容的行)
        last_good_row = -1
        for row in range(h - 1, max(0, h // PLACEHOLDER_HALF_SCAN) - 1, -1):
            row_std = float(arr[row, :, :].std())
            if row_std > PLACEHOLDER_ROW_STD_THRESHOLD:
                last_good_row = row
                break

        if last_good_row < 0 or last_good_row >= h - 1:
            return False  # 没有检测到占位

        placeholder_start = last_good_row + 1

        # 用最后一行有效内容向下延伸 (numpy 广播)
        arr[placeholder_start:, :, :] = arr[last_good_row:last_good_row + 1, :, :]
        Image.fromarray(arr, mode="RGB").save(
            output_path, "JPEG",
            quality=JPEG_QUALITY_PIL, optimize=JPEG_OPTIMIZE_PIL,
        )
        return True
    except Exception:
        return False
