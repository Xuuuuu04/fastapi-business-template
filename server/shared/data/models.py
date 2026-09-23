"""
定义两类数据的基类：公开数据 Data 和流程数据 WorkData。
Data 用于接口和模块之间传递，创建后不可修改；WorkData 只描述一次流程会用到的字段，
由执行器按步骤声明读写，不直接创建实例。
"""

from pydantic import BaseModel, ConfigDict

from shared.data.fields import meaning


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page[Item](Data):
    items: list[Item] = meaning("本页记录")
    total: int = meaning("符合条件的记录总数")
    offset: int = meaning("本页从第几条开始，从 0 计数")
    limit: int = meaning("本页最多返回多少条")


class Nothing(Data):
    pass
