from pydantic import SecretStr

from shared.errors.framework import NotSignedIn
from shared.public import Data, Flow, Module, WorkData, contract, meaning, step


class Token(Data):
    token: SecretStr = meaning("合成登录令牌", secret=True, max_length=64)


class Identity(Data):
    username: str = meaning("身份编号")
    name: str = meaning("名称")
    org_id: str = meaning("组织")
    permissions: list[str] = meaning("已验证权限")


class IdentityWork(Token, WorkData):
    result: Identity = meaning("身份")


resolve = contract(
    "sample_identity.resolve", "解析身份", input=Token, output=Identity, access="public"
)


@step("验证合成会话", reads=["token"], writes=["result"])
def identify(data: IdentityWork) -> None:
    if data.token.get_secret_value() != "opaque-valid":
        raise NotSignedIn("登录会话无效")
    data.result = Identity(
        username="alice", name="示例", org_id="alpha", permissions=["system.diagnostics"]
    )


module = Module(
    "sample_identity",
    "身份解析示例",
    "1",
    provides={resolve: Flow("解析身份", work=IdentityWork, result="result", steps=[identify])},
    identity=resolve,
    identity_header="X-Legacy-Token",
    identity_token="opaque",
)
