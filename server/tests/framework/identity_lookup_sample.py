"""
登录开销演练的独立框架模块：按令牌摘要读取会话，不缓存身份，不使用产品账号。
"""

import hashlib
import json
from dataclasses import replace

from sqlalchemy import Column, MetaData, String, Table, Text, select

from shared.errors.framework import NotSignedIn
from shared.public import Db, Flow, step
from tests.framework.identity_sample import Identity, IdentityWork, module, resolve

sample_metadata = MetaData()
sessions = Table(
    "sample_identity_sessions",
    sample_metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("username", String(64), nullable=False),
    Column("org_id", String(64), nullable=False),
    Column("permissions", Text, nullable=False),
)


# 每个请求实际查询数据库，会话删除或停用立即反映到下一次解析。
class IdentityStore:
    # 只取得框架本次的只读入口。
    def __init__(self, db: Db) -> None:
        self.db = db

    # 不透明凭据只用于摘要查找，不写入运行记录。
    async def lookup(self, token: str) -> Identity:
        digest = hashlib.sha256(token.encode()).hexdigest()
        found = await self.db.first(select(sessions).where(sessions.c.token_hash == digest))
        if found is None:
            raise NotSignedIn("登录会话无效")
        return Identity(
            username=found["username"],
            name="演练用户",
            org_id=found["org_id"],
            permissions=json.loads(found["permissions"]),
        )


# 与正常业务身份解析相同，每次走真实数据库读取。
@step("查询当前有效会话", reads=["token"], writes=["result"])
async def lookup_identity(data: IdentityWork, store: IdentityStore) -> None:
    data.result = await store.lookup(data.token.get_secret_value())


lookup_module = replace(
    module,
    store=IdentityStore,
    tables=(sessions,),
    provides={
        resolve: Flow("查询有效会话", work=IdentityWork, result="result", steps=[lookup_identity]),
    },
)
