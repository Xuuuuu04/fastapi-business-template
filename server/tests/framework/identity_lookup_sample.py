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


class IdentityStore:
    def __init__(self, db: Db) -> None:
        self.db = db

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
