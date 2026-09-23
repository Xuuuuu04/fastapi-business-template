"""
用户权限模块的操作、存储实现和表声明。
"""

from service.user_access import flow, public
from service.user_access.store.sql import SqlAccessStore
from service.user_access.store.tables import orgs, roles, users
from shared.public import Module

module = Module(
    name="user_access",
    title="用户权限",
    version="1",
    provides={
        public.create_org: flow.create_org,
        public.list_orgs: flow.list_orgs,
        public.create_role: flow.create_role,
        public.list_roles: flow.list_roles,
        public.create_user: flow.create_user,
        public.list_users: flow.list_users,
        public.change_user: flow.change_user,
        public.login: flow.login,
    },
    store=SqlAccessStore,
    tables=(orgs, roles, users),
)
