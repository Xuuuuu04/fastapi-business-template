"""
数据库矩阵与进程预算共同选择；控制连接只供创建隔离资源，不直接清空目标数据库。
"""

import os
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


# 程序化调用默认串行，短命令显式设置预算；两个数据库共享总进程预算。
@dataclass(frozen=True)
class CheckOptions:
    database: str = "auto"
    workers: int = 0
    group: str = "all"
    delivery: bool = False

    # 总预算有上限，非法组名在执行子进程前拒绝。
    def __post_init__(self) -> None:
        if not 0 <= self.workers <= 32 or self.group not in {
            "all",
            "pure",
            "module",
            "flow",
            "framework",
        }:
            raise ValueError("检查进程预算或分组无效")


# 测试子进程不继承生产配置，仅保留明确的外部测试服务地址。
def clean_environment() -> dict[str, str]:
    system = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "TZ",
        "SYSTEMROOT",
        "WINDIR",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "UV_CACHE_DIR",
        "TEMPLATE_COPY_RUN",
    }
    allowed = {
        "APP_TEST_REDIS_URL",
        "APP_TEST_S3_ENDPOINT",
        "APP_TEST_S3_ACCESS_KEY",
        "APP_TEST_S3_SECRET_KEY",
        "APP_TEST_S3_BUCKET",
        "APP_TEST_S3_REGION",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in system or key in allowed or key.startswith("LC_")
    }


# 每个数据库使用独立轮次与资源前缀，使用多少worker会进入检查记录。
def suite_environment(
    env: dict[str, str], database: str, postgres: str, workers: int
) -> dict[str, str]:
    result = {**env, "APP_TEST_RUN_ID": uuid.uuid4().hex, "APP_TEST_WORKERS": str(workers)}
    result.pop("APP_TEST_DATABASE_URL", None)
    if database == "postgresql":
        result["APP_TEST_CONTROL_URL"] = postgres
    else:
        result.pop("APP_TEST_CONTROL_URL", None)
    return result


# 没有明确地址不能把PostgreSQL标为已检查，重复矩阵也不会产生两份同库结果。
def databases(postgres: str, requested: str) -> tuple[str, ...]:
    if requested not in {"auto", "sqlite", "postgresql", "both"}:
        raise ValueError("数据库选择无效")
    selection = ("both" if postgres else "sqlite") if requested == "auto" else requested
    if selection in {"postgresql", "both"} and not postgres:
        raise ValueError("PostgreSQL检查必须明确提供隔离测试控制地址")
    return ("sqlite", "postgresql") if selection == "both" else (selection,)


# 两个数据库可以同时运行，总worker数量仍不超过用户设置的预算。
def execute_matrix(
    selected: tuple[str, ...],
    postgres: str,
    command: list[str],
    env: dict[str, str],
    options: CheckOptions,
    run_tests: Callable[..., Any],
    primary_title: str = "默认测试",
) -> list[tuple[str, bool, dict[str, Any], float]]:
    from time import perf_counter

    workers = max(0, options.workers // len(selected))
    arguments = [*command, *(["-n", str(workers)] if workers else [])]

    # 各子进程只写自己的临时结果，控制进程按数据库顺序汇总。
    def execute(database: str) -> tuple[str, bool, dict[str, Any], float]:
        started = perf_counter()
        title = "PostgreSQL 测试" if database == "postgresql" else primary_title
        passed, evidence = run_tests(
            title,
            arguments,
            suite_environment(
                env,
                database,
                postgres,
                workers,
            ),
            database,
        )
        return database, passed, evidence, round(perf_counter() - started, 3)

    if len(selected) > 1 and options.workers > 1:
        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            return list(pool.map(execute, selected))
    result: list[tuple[str, bool, dict[str, Any], float]] = []
    for database in selected:
        if result and result[0][1]:
            env = {**env, "APP_DEVELOPMENT_REPEAT_DATABASE": "1"}
        result.append(execute(database))
    return result
