"""
基础设施实现的登记表：文件存储、缓存、大模型服务商各有哪些实现，配置里写名字就能选。
框架自带的实现登记在这里；项目自己的实现（例如阿里云 OSS）写在自己的文件里，
再加到 app/setup/catalog.py 的 BACKENDS 中，不需要修改框架文件。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from shared.cache.backends import MemoryCache, RedisCache
from shared.config.settings import Settings
from shared.errors.framework import ConfigError
from shared.files.storage import LocalFiles, S3Files, S3Options
from shared.model_calls.providers import OpenAICompatible

Kind = Literal["files", "cache", "model"]
SETTING = {"files": "APP_FILE_STORAGE", "cache": "APP_CACHE_BACKEND", "model": "APP_MODEL_PROVIDER"}


@dataclass(frozen=True)
class Backend:
    kind: Kind
    name: str
    title: str
    make: Callable[[Settings], Any]


# 本地目录文件存储。
def local_files(settings: Settings) -> LocalFiles:
    return LocalFiles(Path(settings.file_root))


# S3 兼容对象存储；没有配置存储桶时拒绝启动。
def s3_files(settings: Settings) -> S3Files:
    if not settings.s3_bucket:
        raise ConfigError(["APP_FILE_STORAGE=s3 时必须配置 APP_S3_BUCKET"])
    secret = settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else ""
    options = S3Options(
        settings.s3_bucket, settings.s3_endpoint, settings.s3_region, settings.s3_access_key, secret
    )
    return S3Files(options)


# Redis 缓存；没有配置地址时拒绝启动。
def redis_cache(settings: Settings) -> RedisCache:
    if not settings.cache_url:
        raise ConfigError(["APP_CACHE_BACKEND=redis 时必须配置 APP_CACHE_URL"])
    return RedisCache(settings.cache_url)


# OpenAI 兼容接口的大模型服务商。
def openai_provider(settings: Settings) -> OpenAICompatible:
    key = settings.model_api_key.get_secret_value() if settings.model_api_key else ""
    return OpenAICompatible(
        settings.model_base_url, key, settings.model_name, settings.model_timeout
    )


BUILTIN: tuple[Backend, ...] = (
    Backend("files", "local", "本地目录", local_files),
    Backend("files", "s3", "S3 兼容对象存储", s3_files),
    Backend("cache", "memory", "进程内缓存", lambda settings: MemoryCache()),
    Backend("cache", "redis", "Redis", redis_cache),
    Backend("model", "openai", "OpenAI 兼容接口", openai_provider),
)


# 按配置的名字创建一种实现；名字不存在或重复登记时拒绝启动，并列出可选的名字。
def create(kind: Kind, name: str, settings: Settings, extra: Sequence[Backend] = ()) -> Any:
    found = [item for item in (*BUILTIN, *extra) if item.kind == kind and item.name == name]
    if len(found) > 1:
        raise ConfigError([f"{SETTING[kind]} 的实现 {name} 被重复登记"])
    if not found:
        choices = "、".join(item.name for item in (*BUILTIN, *extra) if item.kind == kind)
        raise ConfigError([f"{SETTING[kind]}={name} 没有登记，可选：{choices}"])
    return found[0].make(settings)
