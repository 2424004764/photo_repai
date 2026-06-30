"""修复上下文(消除循环依赖)。

策略函数通过 RepairContext 拿到输入/输出路径等共享信息,而不是绑在某个类上。
这样每个策略文件可以独立被 import、独立被测试。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairContext:
    """一次修复会话所需的全部上下文(不可变,避免策略间意外修改)。"""

    src_path: str       # 原图绝对路径
    output_path: str    # 修复后输出路径(固定为 <src_name>_fixed.jpg)
    output_dir: str     # 输出目录
    ext: str            # 原图扩展名(小写,带点)
