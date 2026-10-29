from decimal import Decimal

import pytest
from pydantic import ValidationError

from shared.public import Data, meaning


class Amount(Data):
    value: Decimal = meaning("精确金额", unit="元")


def test_public_data_rejects_unknown_and_mutation() -> None:
    with pytest.raises(ValidationError):
        Amount(value="1.25", surprise=True)
    value = Amount(value=Decimal("1.25"))
    with pytest.raises(ValidationError):
        value.value = Decimal("2.50")
    assert value.value == Decimal("1.25")


def test_decimal_contract_round_trip() -> None:
    value = Amount.model_validate_json('{"value":"0.01"}')
    assert Amount.model_validate_json(value.model_dump_json()).value == Decimal("0.01")
