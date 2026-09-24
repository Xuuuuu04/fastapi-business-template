"""
商品目录的 HTTP 接口（第 1 版）。路由只做参数转换，业务都在 product_catalog 模块的流程中。
只导入模块的 public.py；接口格式要变时新建 v2 文件，转换后调用同一个操作。
"""

from typing import Annotated

from fastapi import APIRouter, File, Path, Query, Response, UploadFile

from app.api.identity import require
from app.api.replies import responses_for
from app.api.runner import RunDep
from service.product_catalog import public as catalog
from shared.errors.framework import InvalidInput
from shared.exchange.sheets import MEDIA, Kind, read_sheet, write_sheet

router = APIRouter(prefix="/api/v1/products", tags=["商品目录"])

HEADERS = {"code": "编码", "name": "名称", "price": "单价", "on_sale": "在售"}
REQUIRED = {"code": "编码", "name": "名称"}
COLUMNS = {**{title: field for field, title in HEADERS.items()}, **{f: f for f in HEADERS}}

ProductNumber = Annotated[int, Path(gt=0, description="商品编号")]


# 分页查询商品，可以按在售状态筛选。
@router.get(
    "",
    summary="查询商品",
    operation_id="list_products",
    response_model=catalog.ProductPage,
    responses=responses_for(catalog.list_products),
)
async def list_products(
    run: RunDep, query: Annotated[catalog.ProductQuery, Query()]
) -> catalog.ProductPage:
    return await run(catalog.list_products, query)


# 按 R-03 从 CSV 或 Excel 批量导入商品；有问题的行不导入，结果中列出行号和原因。
@router.post(
    "/import",
    summary="批量导入商品",
    operation_id="import_products",
    response_model=catalog.ImportResult,
    responses=responses_for(catalog.import_products),
)
async def import_products(
    run: RunDep, upload: Annotated[UploadFile, File(description="CSV（UTF-8）或 .xlsx 文件")]
) -> catalog.ImportResult:
    require(run.caller, catalog.import_products.access)
    rows = read_sheet(await upload.read(), upload.filename or "", COLUMNS, REQUIRED)
    if not rows:
        raise InvalidInput("文件中没有数据行")
    lines = [catalog.ImportLine(row=number, **values) for number, values in rows]
    return await run(catalog.import_products, catalog.ImportRequest(lines=lines))


# 按 R-04 导出商品为 CSV 或 Excel，列与导入相同，改好后可以直接再导入。
@router.get(
    "/export",
    summary="导出商品",
    operation_id="export_products",
    responses=responses_for(catalog.export_products),
)
async def export_products(
    run: RunDep,
    on_sale: Annotated[bool | None, Query(description="只导出在售或停售，不写则全部导出")] = None,
    kind: Annotated[Kind, Query(alias="format", description="csv 或 xlsx")] = "csv",
) -> Response:
    found = await run(catalog.export_products, catalog.ExportQuery(on_sale=on_sale))
    rows = [item.model_dump() for item in found.items]
    headers = {"Content-Disposition": f'attachment; filename="products.{kind}"'}
    return Response(write_sheet(rows, HEADERS, kind), media_type=MEDIA[kind], headers=headers)


# 按编号读取商品。
@router.get(
    "/{product_id}",
    summary="读取商品",
    operation_id="get_product",
    response_model=catalog.ProductView,
    responses=responses_for(catalog.get_product),
)
async def get_product(product_id: ProductNumber, run: RunDep) -> catalog.ProductView:
    return await run(catalog.get_product, catalog.ProductId(product_id=product_id))


# 新建商品。
@router.post(
    "",
    status_code=201,
    summary="新建商品",
    operation_id="create_product",
    response_model=catalog.ProductView,
    responses=responses_for(catalog.create_product),
)
async def create_product(body: catalog.ProductInput, run: RunDep) -> catalog.ProductView:
    return await run(catalog.create_product, body)


# 修改商品的全部字段。
@router.put(
    "/{product_id}",
    summary="修改商品",
    operation_id="update_product",
    response_model=catalog.ProductView,
    responses=responses_for(catalog.update_product),
)
async def update_product(
    product_id: ProductNumber, body: catalog.ProductInput, run: RunDep
) -> catalog.ProductView:
    change = catalog.ProductChange(product_id=product_id, **body.model_dump())
    return await run(catalog.update_product, change)


# 删除商品，成功时返回空响应。
@router.delete(
    "/{product_id}",
    status_code=204,
    summary="删除商品",
    operation_id="delete_product",
    responses=responses_for(catalog.delete_product),
)
async def delete_product(product_id: ProductNumber, run: RunDep) -> Response:
    await run(catalog.delete_product, catalog.ProductId(product_id=product_id))
    return Response(status_code=204)
