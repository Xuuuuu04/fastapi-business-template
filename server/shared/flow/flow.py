"""
定义流程 Flow：把步骤按顺序连起来，并指定哪个字段作为返回结果。
流程只描述顺序和条件，不写业务计算；计算写在步骤里。
"""

from collections.abc import Sequence

from shared.data.models import WorkData
from shared.flow.step import Step


class Flow:
    # 记录流程名称、流程数据类型、结果字段和步骤顺序。
    def __init__(
        self, title: str, *, work: type[WorkData], result: str, steps: Sequence[Step]
    ) -> None:
        self.title = title
        self.work = work
        self.result = result
        self.steps: tuple[Step, ...] = tuple(steps)
