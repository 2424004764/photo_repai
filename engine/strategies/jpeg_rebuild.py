"""JPEG 段级字节重建策略(策略 4)。

对 JPEG 文件做无损字节级重建:
1. 用标准默认量化表 / Huffman 表替换损坏的 DQT/DHT 段
2. 跳过所有 DQT/DHT 段的 payload(因为已经用了默认表)
3. 其他段原样拷贝
4. SOS 后的熵编码数据原样拷贝

★ 截断文件跳过此策略(熵编码不完整,加伪 EOI 会导致占位色)
"""
from __future__ import annotations

import os

from ._context import RepairContext

# 标准 JPEG 亮度量化表 (Annex K, Table K.1)
_LUM_DQT = bytes([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
])
# 标准 DC Huffman 表
_DC_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
_DC_VALS = list(range(12))
# 标准 AC Huffman 表
_AC_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7d]
_AC_VALS = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
    0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08,
    0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16,
    0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
    0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
    0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
    0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7,
    0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6,
    0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5,
    0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4,
    0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
    0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea,
    0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
    0xf9, 0xfa,
]


def build_default_segments() -> bytes:
    """构造默认 DQT + DHT 段字节流,用于回填损坏的 JPEG。"""
    out = bytearray()

    # DQT 段: FFDB 00 43 00 [64 bytes luminance table]
    out.extend(b"\xff\xdb")
    out.extend((2 + 1 + 64).to_bytes(2, "big"))  # length = 67
    out.append(0x00)  # 精度 0 (8bit) + 表 ID 0
    out.extend(_LUM_DQT)

    # DHT DC 段: FFC4 LL LL TC|TH [16 bits] [vals]
    dc_vals = bytes(_DC_VALS)
    out.extend(b"\xff\xc4")
    out.extend((2 + 1 + 16 + len(dc_vals)).to_bytes(2, "big"))
    out.append(0x00)  # DC table 0
    out.extend(bytes(_DC_BITS))
    out.extend(dc_vals)

    # DHT AC 段
    ac_vals = bytes(_AC_VALS)
    out.extend(b"\xff\xc4")
    out.extend((2 + 1 + 16 + len(ac_vals)).to_bytes(2, "big"))
    out.append(0x10)  # AC table 0
    out.extend(bytes(_AC_BITS))
    out.extend(ac_vals)

    return bytes(out)


def try_jpeg_rebuild(ctx: RepairContext) -> tuple[bool, str]:
    """对 JPEG 做字节级重建,保留熵编码,用默认表替换损坏的 DQT/DHT。"""
    with open(ctx.src_path, "rb") as f:
        data = f.read()

    if len(data) < 4:
        return False, "文件太小 (<4 字节)"

    # ★ 截断检测:无 EOI 结尾的 JPEG 不适合字节级重建
    if not data.endswith(b"\xff\xd9"):
        return False, "原图被截断 (无 EOI),跳过无损重建"

    # 找 SOI
    if data[:2] != b"\xff\xd8":
        idx = data.find(b"\xff\xd8")
        if idx < 0:
            return False, "找不到 SOI 标记 (FFD8)"
        data = data[idx:]

    if b"\xff\xc0" not in data:
        return False, "缺少 SOF 帧头,无法重建"

    # 输出:SOI + 默认 DQT/DHT + 原始其余段(DQT/DHT 跳过)
    out = bytearray(b"\xff\xd8")
    out.extend(build_default_segments())

    i = 2  # 跳过 SOI
    last_sos_idx = -1
    truncated = False
    skipped_dqt = skipped_dht = 0

    while i < len(data):
        # 跳过所有 FF 填充
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            truncated = True
            break

        marker = data[i]
        i += 1

        # 无长度字段的标记:EOI / RST
        if marker == 0xD9:  # EOI
            out.extend(b"\xff\xd9")
            truncated = False
            break
        if 0xD0 <= marker <= 0xD7:  # RST0..RST7
            out.extend(b"\xff")
            out.append(marker)
            continue

        # 有长度字段的标记
        if i + 2 > len(data):
            truncated = True
            break
        seg_len = (data[i] << 8) | data[i + 1]
        if seg_len < 2:
            truncated = True
            break
        # seg_len 字节 = length_field(2) + payload(seg_len-2)
        seg_end = i + seg_len
        if seg_end > len(data):
            truncated = True
            break

        # 写 marker + length_field + payload
        out.extend(b"\xff")
        out.append(marker)
        out.extend(data[i:seg_end])

        # ★ DQT / DHT:跳过 payload(已用默认表)
        if marker == 0xDB:
            skipped_dqt += 1
            i = seg_end
            continue
        if marker == 0xC4:
            skipped_dht += 1
            i = seg_end
            continue

        # SOS:后续是熵编码数据,直接拷贝到下一个 marker 或 EOF
        if marker == 0xDA:
            i = seg_end
            while i < len(data):
                if data[i] == 0xFF and i + 1 < len(data):
                    nxt = data[i + 1]
                    if nxt == 0x00:
                        # FF 00 = 字面 FF 填充字节
                        out.extend(data[i:i + 2])
                        i += 2
                    elif 0xD0 <= nxt <= 0xD7:
                        # RST 标记
                        out.extend(data[i:i + 2])
                        i += 2
                    else:
                        # 下一个 marker,跳出
                        break
                else:
                    out.append(data[i])
                    i += 1
            last_sos_idx = len(out)
            continue

        # 普通段:已拷贝,前进
        i = seg_end

    # 截断但有 SOS 时补 EOI
    if truncated and last_sos_idx > 0:
        out.extend(b"\xff\xd9")

    if last_sos_idx < 0:
        return False, "未找到 SOS 扫描段,无可解码图像数据"

    os.makedirs(ctx.output_dir, exist_ok=True)
    with open(ctx.output_path, "wb") as f:
        f.write(bytes(out))

    suffix = ""
    if skipped_dqt or skipped_dht:
        suffix = f" (跳过 {skipped_dqt} 个 DQT, {skipped_dht} 个 DHT,使用默认表)"
    return True, f"JPEG 字节级无损重建,使用默认表替换{suffix}"
