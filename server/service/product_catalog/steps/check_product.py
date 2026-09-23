"""
商品输入的整理规则。纯计算，不读写数据库。
"""

from service.product_catalog.data import CreateWork
from shared.public import step


# 按 R-01 整理商品编码：去掉首尾空白，转成大写。
@step("整理商品编码", reads=["code"], writes=["clean_code"], rule="R-01")
def clean_code(data: CreateWork) -> None:
    data.clean_code = data.code.strip().upper()
