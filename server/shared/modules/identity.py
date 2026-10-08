"""
产品可在模块声明中提供不透明登录令牌的身份解析操作，框架不导入任何业务包。
只启用一个解析入口；JWT仍使用原签名与有效期校验，旧模板没有此声明时行为不变。
"""

import re
from collections.abc import Sequence

from pydantic import SecretStr

from shared.access.caller import PUBLIC
from shared.modules.module import Module


# 检查解析操作归属、输入与输出，关闭模块后不留下认证旁路。
def check_identity(modules: Sequence[Module]) -> list[str]:
    declared = [module for module in modules if module.identity is not None]
    problems = [
        f"模块 {module.name} 设置了identity_header但没有identity操作"
        for module in modules
        if module.identity_header and module.identity is None
    ]
    if len(declared) > 1:
        problems.append("只能启用一个登录身份解析操作")
    for module in declared:
        if module.identity_token not in ("jwt", "opaque"):
            problems.append(f"模块 {module.name} 的identity_token必须为jwt或opaque")
        operation = module.identity
        if operation is None:
            continue
        if operation not in module.provides or not operation.entry or operation.access != PUBLIC:
            problems.append(f"模块 {module.name} 的identity必须是本模块公开提供的public操作")
        fields = operation.input.model_fields
        if set(fields) != {"token"} or fields["token"].annotation not in (str, SecretStr):
            problems.append(f"身份操作 {operation.name} 输入必须只有str或SecretStr的token")
        expected = {"username": str, "name": str, "org_id": str, "permissions": list[str]}
        for name, annotation in expected.items():
            found = operation.output.model_fields.get(name)
            if found is None or found.annotation != annotation:
                problems.append(f"身份操作 {operation.name} 输出字段{name}类型不匹配")
        header = module.identity_header
        if header and (
            not re.fullmatch(r"[A-Za-z0-9-]+", header)
            or header.lower() in ("authorization", "x-api-key")
        ):
            problems.append(f"模块 {module.name} 的identity_header不能覆盖标准凭据头")
    return problems
