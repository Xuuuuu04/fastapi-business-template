"""
嵌套敏感字段在取值摘要序列化前阻止整个容器的原文记录。
"""

from typing import Any

import pytest
from pydantic import model_serializer

from shared.data.fields import FieldNote
from shared.public import Data, meaning
from shared.records.values import describe_value


# 测试敏感字段的模型；序列化函数不应在生成安全摘要时被调用。
class Credential(Data):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)

    # 如果先序列化再隐藏敏感值，这里会直接让测试失败。
    @model_serializer
    def prevent_serialization(self) -> dict[str, str]:
        raise AssertionError("含敏感字段的模型不应序列化")


# 嵌套模型也必须传播内部敏感性。
class Response(Data):
    credential: Credential = meaning("凭据")


# 一个敏感值不论在模型、列表或字典的哪一层都不能出现。
@pytest.mark.parametrize("container", ["model", "list", "dict", "tuple", "nested"])
def test_nested_secret_stays_out_of_value_summary(container: str) -> None:
    credential = Credential(user="测试用户", token="synthetic-sensitive-token")
    values: dict[str, Any] = {
        "model": credential,
        "list": [credential],
        "dict": {"items": [{"credential": credential}]},
        "tuple": (credential,),
        "nested": Response(credential=credential),
    }
    summary = describe_value(values[container], FieldNote("result", "结果", log_value=True))
    assert summary == "结果：已写入（敏感字段，不记录内容）"


# 循环引用不让检查无限递归，后面的敏感值仍然要检查。
def test_cyclic_container_checks_remaining_secret() -> None:
    values: list[Any] = []
    values.append(values)
    values.append(Credential(user="测试用户", token="synthetic-sensitive-token"))
    summary = describe_value(values, FieldNote("result", "结果", log_value=True))
    assert summary == "结果：已写入（敏感字段，不记录内容）"


# 不含敏感字段的公开内容仍保持原有短文本格式。
def test_public_value_summary_remains_readable() -> None:
    note = FieldNote("result", "结果", log_value=True)
    assert describe_value({"count": 3}, note) == "结果：{'count': 3}"
