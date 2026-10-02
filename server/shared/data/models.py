"""
定义两类数据的基类：公开数据 Data 和流程数据 WorkData。
Data 用于接口和模块之间传递，创建后不可修改；WorkData 只描述一次流程会用到的字段，
由执行器按步骤声明读写，不直接创建实例。
"""

from pydantic import BaseModel, ConfigDict

from shared.data.fields import meaning


# 模块公开输入与输出的基础格式，统一检查字段和序列化方式。
class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# 同一流程各步骤共享的数据格式，由步骤声明限制读写范围。
class WorkData(BaseModel):
    model_config = ConfigDict(extra="forbid")


# 按起始位置分页的结果，包含本页数据与总数。
class Page[Item](Data):
    items: list[Item] = meaning("本页记录")
    total: int = meaning("符合条件的记录总数")
    offset: int = meaning("本页从第几条开始，从 0 计数")
    limit: int = meaning("本页最多返回多少条")


# 按上一页位置继续读取的结果，包含本页数据与继续位置。
class CursorPage[Item](Data):
    items: list[Item] = meaning("本页记录")
    next_after: str = meaning("取下一页时作为 after 传回的位置", empty="已经是最后一页", default="")


# 表示操作没有输入内容或没有返回内容的统一数据格式。
class Nothing(Data):
    pass
