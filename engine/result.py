"""修复结果的数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RepairResult:
    """单次修复尝试的结果。"""

    success: bool
    strategy: str            # 实际成功的策略名,如 "OpenCV"
    message: str             # 简要说明
    output_path: Optional[str] = None
    attempts: list[str] = field(default_factory=list)  # 每个策略的尝试记录
