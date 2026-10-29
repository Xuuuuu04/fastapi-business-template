from collections.abc import Sequence

from shared.data.models import WorkData
from shared.flow.step import Step


class Flow:
    def __init__(
        self, title: str, *, work: type[WorkData], result: str, steps: Sequence[Step]
    ) -> None:
        self.title = title
        self.work = work
        self.result = result
        self.steps: tuple[Step, ...] = tuple(steps)
