"""
定义模块对外提供的操作约定 contract()。
约定写在模块的 public.py 中，说明操作名称、中文用途、输入输出类型、所需权限和可能的业务错误；
其他模块和接口层只凭约定调用，不导入实现。实现由模块声明 module.py 把约定和流程对应起来。
"""

from dataclasses import dataclass

from shared.data.models import Data
from shared.errors.kinds import BusinessError


# 一个模块公开操作的输入、输出、权限和允许失败类型。
@dataclass(frozen=True, eq=False)
class Contract[In: Data, Out: Data]:
    name: str
    title: str
    input: type[In]
    output: type[Out]
    access: str
    errors: tuple[type[BusinessError], ...] = ()
    entry: bool = True
    timeout: float = 30.0
    audit: bool = False
    stream: bool = False

    # 约定名称的第一段是提供它的模块名。
    @property
    def module(self) -> str:
        return self.name.split(".", 1)[0]

    # 约定名称的第二段是操作名。
    @property
    def action(self) -> str:
        return self.name.split(".", 1)[-1]


# 声明一个操作约定；entry=False 表示只允许其他模块调用，不能从接口或任务直接调用。
def contract[In: Data, Out: Data](
    name: str,
    title: str,
    *,
    input: type[In],
    output: type[Out],
    access: str,
    errors: tuple[type[BusinessError], ...] = (),
    entry: bool = True,
    timeout: float = 30.0,
    audit: bool = False,
    stream: bool = False,
) -> Contract[In, Out]:
    return Contract(name, title, input, output, access, errors, entry, timeout, audit, stream)
