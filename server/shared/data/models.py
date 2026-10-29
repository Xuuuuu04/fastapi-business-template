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


class CursorPage[Item](Data):
    items: list[Item] = meaning("本页记录")
    next_after: str = meaning("取下一页时作为 after 传回的位置", empty="已经是最后一页", default="")


class Nothing(Data):
    pass
