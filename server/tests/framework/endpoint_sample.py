"""
独立的读/写上游协议样例，只供框架测试，不登记模板业务。
"""

from shared.public import (
    Data,
    Endpoint,
    Flow,
    Module,
    RemoteClient,
    WorkData,
    contract,
    meaning,
    remote,
    step,
)

upstream = remote("protocol_probe", "测试上游", retries=1)


# 请求字段由框架序列化。
class Request(Data):
    sku: str = meaning("商品编号")


# 成功与确定拒绝使用同一回执结构，受理含义由业务自行核对。
class Receipt(Data):
    accepted: bool = meaning("是否受理")
    count: int = meaning("记录数量")


read_endpoint = Endpoint(
    "protocol_probe.read",
    "POST",
    "/read",
    input=Request,
    output=Receipt,
    effect="read",
)
write_endpoint = Endpoint(
    "protocol_probe.write",
    "POST",
    "/write",
    input=Request,
    output=Receipt,
    effect="write",
    accepted_statuses=(409,),
    unknown_on=(202,),
)
read = contract("endpoint_probe.read", "读上游", input=Request, output=Receipt, access="public")
write = contract("endpoint_probe.write", "写上游", input=Request, output=Receipt, access="public")


# 保持原来的短操作结构。
class Work(WorkData):
    sku: str = meaning("商品编号")
    result: Receipt = meaning("回执")


# POST读取以effect为准，可在暂时故障后重试。
@step("查询上游", reads=["sku"], writes=["result"], remotes=[upstream], endpoints=[read_endpoint])
async def read_receipt(data: Work, remote: RemoteClient) -> None:
    reply = await remote.call(upstream, read_endpoint, Request(sku=data.sku))
    data.result = reply.data


# 写入不确定时暂停，不重发整个业务操作。
@step("修改上游", reads=["sku"], writes=["result"], remotes=[upstream], endpoints=[write_endpoint])
async def write_receipt(data: Work, remote: RemoteClient) -> None:
    reply = await remote.call(upstream, write_endpoint, Request(sku=data.sku))
    data.result = reply.data


module = Module(
    "endpoint_probe",
    "上游协议测试",
    "1",
    {
        read: Flow("读上游", work=Work, result="result", steps=[read_receipt]),
        write: Flow("写上游", work=Work, result="result", steps=[write_receipt]),
    },
    remotes=(upstream,),
    endpoints=(read_endpoint, write_endpoint),
)
