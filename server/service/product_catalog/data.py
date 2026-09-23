"""
商品目录的公开数据、流程数据和业务错误。
公开数据用于接口和其他模块；流程数据只在本模块的流程中使用。
字段含义见 doc/product_catalog/rules.md。
"""

from datetime import datetime
from decimal import Decimal

from shared.public import BusinessError, Data, Kind, Nothing, Page, WorkData, meaning


class ProductInput(Data):
    code: str = meaning(
        "商品编码，保存前去掉首尾空白并转成大写",
        rule="R-01",
        example="A-100",
        min_length=1,
        max_length=40,
    )
    name: str = meaning("商品名称", example="打印纸", min_length=1, max_length=80)
    price: Decimal | None = meaning(
        "单价",
        unit="元",
        empty="尚未定价，不能用于报价",
        default=None,
        rule="R-02",
        ge=0,
        decimal_places=2,
        max_digits=12,
    )
    on_sale: bool = meaning("是否在售；停售的商品不能用于报价", rule="R-02", default=True)


class ProductChange(ProductInput):
    product_id: int = meaning("要修改的商品编号", gt=0)


class ProductId(Data):
    product_id: int = meaning("商品编号", gt=0)


class ProductQuery(Data):
    offset: int = meaning("从第几条开始，从 0 计数", default=0, ge=0)
    limit: int = meaning("本页最多返回多少条", default=20, ge=1, le=100)
    on_sale: bool | None = meaning("只看在售或只看停售", empty="不按在售状态筛选", default=None)


class ProductView(Data):
    id: int = meaning("商品编号")
    code: str = meaning("商品编码", rule="R-01")
    name: str = meaning("商品名称")
    price: Decimal | None = meaning("单价", unit="元", empty="尚未定价", rule="R-02")
    on_sale: bool = meaning("是否在售", rule="R-02")
    updated_at: datetime = meaning("最后修改时间（UTC）")


ProductPage = Page[ProductView]


class PriceQuery(Data):
    codes: list[str] = meaning("要查询单价的商品编码", min_length=1, max_length=200)


class PriceList(Data):
    prices: dict[str, Decimal] = meaning(
        "可以报价的商品单价，按商品编码对应", unit="元", rule="R-02"
    )
    missing: list[str] = meaning("不能报价的商品编码：不存在、已停售或尚未定价", rule="R-02")


class ProductMissing(BusinessError):
    code = "product_missing"
    kind = Kind.NOT_FOUND
    message = "商品不存在"


class CodeUsed(BusinessError):
    code = "product_code_used"
    kind = Kind.CONFLICT
    message = "商品编码已被其他商品使用"


class ListWork(WorkData):
    offset: int = meaning("从第几条开始")
    limit: int = meaning("本页最多返回多少条")
    on_sale: bool | None = meaning("在售状态筛选", empty="不筛选")
    page: ProductPage = meaning("查询到的一页商品")


class GetWork(WorkData):
    product_id: int = meaning("商品编号")
    product: ProductView = meaning("读取到的商品")


class CreateWork(WorkData):
    code: str = meaning("调用方填写的商品编码")
    name: str = meaning("商品名称")
    price: Decimal | None = meaning("单价", unit="元", empty="尚未定价")
    on_sale: bool = meaning("是否在售")
    clean_code: str = meaning("整理后的商品编码", rule="R-01", log_value=True)
    product: ProductView = meaning("保存后的商品")


class UpdateWork(CreateWork):
    product_id: int = meaning("要修改的商品编号")


class DeleteWork(WorkData):
    product_id: int = meaning("要删除的商品编号")
    done: Nothing = meaning("删除完成的标记")


class PriceWork(WorkData):
    codes: list[str] = meaning("要查询单价的商品编码")
    prices: PriceList = meaning("查询结果")
