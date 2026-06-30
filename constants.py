"""
项目集中常量。

所有原本散落在 main.py 各处的魔术数字、超时、阈值、UI 字符串都集中到这里,
方便统一调整和复用。
"""
from __future__ import annotations

# ---------- 窗口 / GUI ----------
WINDOW_GEOMETRY = "780x680"
WINDOW_TITLE = "AI & 传统图片修复工具 v2.1"

# 候选 CJK 字体,按优先级逐个尝试 (Windows / macOS / Linux 通用回退顺序)
CJK_FONT_FALLBACK: tuple[str, ...] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimHei",
    "微软雅黑",
    "PingFang SC",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
)

# 支持的图片扩展名(单/批量模式共用)
SUPPORTED_EXTS: tuple[str, ...] = (
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff",
)

# ---------- 输出命名 ----------
OUTPUT_SUFFIX = "_fixed"
OUTPUT_EXT = ".jpg"
BATCH_SUBFOLDER = "_repaired"

# ---------- JPEG 写出质量 ----------
JPEG_QUALITY_PIL = 100        # PIL save() 的 quality
JPEG_OPTIMIZE_PIL = True      # PIL save() 是否启用 Huffman 优化
JPEG_PROGRESSIVE_PIL = False  # PIL save() 是否用渐进式 JPEG
JPEG_QUALITY_IMAGEMAGICK = 95 # ImageMagick -quality 参数
JPEG_QUALITY_FFMPEG = 1       # FFmpeg -q:v 参数(1=最高)

# ---------- 超时(秒) ----------
PROBE_TIMEOUT_SEC = 5        # 探测外部工具版本时
REPAIR_TIMEOUT_SEC = 120     # 实际调用外部工具修复时

# ---------- PIL Parser / 字节扫描 ----------
PARSER_CHUNK_BYTES = 8192    # _try_pil 第二轮 Parser.feed 的读取粒度
EOI_SCAN_TAIL_BYTES = 64     # _is_input_truncated 检查 EOI 的尾部窗口

# ---------- 截断文件占位修复阈值 ----------
PLACEHOLDER_MIN_HEIGHT = 20       # 高度小于此值直接放弃修复
PLACEHOLDER_HALF_SCAN = 2         # 从底部往上最多扫到 1/2 处
PLACEHOLDER_ROW_STD_THRESHOLD = 10.0  # 行方差阈值(> 此值认为是真实内容)

# ---------- GUI 质量警告阈值(单/批量) ----------
QUALITY_WARN_RATIO_LOW = 70    # 修复后 < 原大小 70% 警告可能画质损失
QUALITY_WARN_RATIO_HIGH = 95   # 修复后 >= 原大小 95% 显示高质量保留
