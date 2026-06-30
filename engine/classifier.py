"""图片三态分类器:clean / repairable / unrepairable。

在 ImageRepairer 之上提供更细粒度的"健康度"判断:
- clean        : PIL 严格模式能开,无需任何修复
- repairable   : 损坏,但 7 级级联能修(返回哪个策略可以救)
- unrepairable : 损坏,级联全失败(返回最后错误信息)

注意:这个函数会实际跑级联,所以比 is_image_clean 慢很多。
如果只是要快查"是不是已经坏了",用 is_image_clean 即可。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from .repairer import ImageRepairer
from .strategies._common import is_image_clean


@dataclass(frozen=True)
class ImageClassification:
    """单张图片的三态分类结果。"""

    state: str                                # "clean" | "repairable" | "unrepairable"
    strategy: Optional[str] = None            # state=="repairable" 时指明哪个策略能修
    message: Optional[str] = None             # repairable 时是策略消息;unrepairable 时是最后错误
    attempts: list[str] = field(default_factory=list)  # 级联跑过的每一步尝试(clean 时为空)

    @property
    def is_clean(self) -> bool:
        return self.state == "clean"

    @property
    def is_repairable(self) -> bool:
        return self.state == "repairable"

    @property
    def is_unrepairable(self) -> bool:
        return self.state == "unrepairable"


def classify_image(path: str, output_dir: Optional[str] = None) -> ImageClassification:
    """三态判定一张图片的"健康度"。

    Args:
        path: 原图绝对路径
        output_dir: 级联跑出来的 _fixed.jpg 写到哪。
                    默认 None 时用临时目录,跑完即删,不污染磁盘。

    Returns:
        ImageClassification,根据 state 取值:
        - "clean":         完全没问题(attempts 为空)
        - "repairable":    能修,看 strategy 字段;attempts 含完整级联日志
        - "unrepairable":  救不了,看 message 字段;attempts 含完整级联日志
    """
    # 1. 快速路径:本来就是好的(不跑级联,所以 attempts 为空)
    if is_image_clean(path):
        return ImageClassification(state="clean")

    # 2. 跑级联;用临时目录避免污染用户磁盘
    cleanup = output_dir is None
    workdir = output_dir or tempfile.mkdtemp(prefix="photo_classify_")
    try:
        repairer = ImageRepairer(path, output_dir=workdir)
        result = repairer.repair()
        if result.success:
            return ImageClassification(
                state="repairable",
                strategy=result.strategy,
                message=result.message,
                attempts=result.attempts,
            )
        return ImageClassification(
            state="unrepairable",
            message=result.message,
            attempts=result.attempts,
        )
    finally:
        if cleanup and os.path.isdir(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
