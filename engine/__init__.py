"""修复引擎包。

公开 API:
- ImageRepairer:对一个文件做多策略级联修复
- RepairResult:修复结果的数据结构
- available_external_engines:探测本机装了哪些外部解码器
- classify_image / ImageClassification:三态健康度分类(clean/repairable/unrepairable)
"""
from __future__ import annotations

from .classifier import ImageClassification, classify_image
from .detection import available_external_engines
from .repairer import ImageRepairer
from .result import RepairResult

__all__ = [
    "ImageRepairer",
    "RepairResult",
    "available_external_engines",
    "ImageClassification",
    "classify_image",
]
