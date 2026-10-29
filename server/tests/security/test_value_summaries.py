from typing import Any

import pytest
from pydantic import model_serializer

from shared.data.fields import FieldNote
from shared.public import Data, meaning
from shared.records.values import describe_value


class Credential(Data):
    user: str = meaning("用户名")
    token: str = meaning("访问令牌", secret=True)

    @model_serializer
    def prevent_serialization(self) -> dict[str, str]:
        raise AssertionError("含敏感字段的模型不应序列化")


class Response(Data):
    credential: Credential = meaning("凭据")


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


def test_cyclic_container_checks_remaining_secret() -> None:
    values: list[Any] = []
    values.append(values)
    values.append(Credential(user="测试用户", token="synthetic-sensitive-token"))
    summary = describe_value(values, FieldNote("result", "结果", log_value=True))
    assert summary == "结果：已写入（敏感字段，不记录内容）"


def test_public_value_summary_remains_readable() -> None:
    note = FieldNote("result", "结果", log_value=True)
    assert describe_value({"count": 3}, note) == "结果：{'count': 3}"
