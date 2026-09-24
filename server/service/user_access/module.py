"""
用户权限模块的操作、存储实现、表和每日清理刷新令牌的任务。
"""

from datetime import time

from service.user_access import flow, public
from service.user_access.store.sql import SqlAccessStore
from service.user_access.store.tables import orgs, refresh_tokens, roles, users
from shared.public import JobPlan, Module, Nothing, Retry, Schedule

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
        public.refresh: flow.refresh,
        public.logout: flow.logout,
        public.change_password: flow.change_password,
        public.purge_sessions: flow.purge_sessions,
    },
    store=SqlAccessStore,
    tables=(orgs, roles, users, refresh_tokens),
    jobs=(JobPlan(public.purge_sessions, retry=Retry(times=2), repeat_safe=True, max_queued=10),),
    schedules=(
        Schedule(
            name="purge_sessions_daily",
            title="每天清理过期和作废的刷新令牌",
            contract=public.purge_sessions,
            input=Nothing(),
            daily_at=time(4, 0),
        ),
    ),
)
