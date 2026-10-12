"""
公开数据的类型、额外字段和不可变性在纯计算组验证，不建立应用或数据库。
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from shared.public import Data, meaning


# 合成金额类型只用于检查公开数据，不含产品业务规则。
class Amount(Data):
    value: Decimal = meaning("精确金额", unit="元")


# 公开数据不能接受未声明的字段或被后续步骤改写。
def test_public_data_rejects_unknown_and_mutation() -> None:
    with pytest.raises(ValidationError):
        Amount(value="1.25", surprise=True)
    value = Amount(value=Decimal("1.25"))
    with pytest.raises(ValidationError):
        value.value = Decimal("2.50")
    assert value.value == Decimal("1.25")


# JSON中的金额可以按明确类型读取，精确小数不会经过二进制浮点计算。
def test_decimal_contract_round_trip() -> None:
    value = Amount.model_validate_json('{"value":"0.01"}')
    assert Amount.model_validate_json(value.model_dump_json()).value == Decimal("0.01")
