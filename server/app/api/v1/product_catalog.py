"""
商品目录的 HTTP 接口（第 1 版）。路由只做参数转换，业务都在 product_catalog 模块的流程中。
只导入模块的 public.py；接口格式要变时新建 v2 文件，转换后调用同一个操作。
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from app.api.replies import responses_for
from app.api.runner import RunDep
from service.product_catalog import public as catalog

router = APIRouter(prefix="/api/v1/products", tags=["商品目录"])

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
