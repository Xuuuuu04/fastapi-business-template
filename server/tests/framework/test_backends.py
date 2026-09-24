"""
基础设施实现登记表：配置写名字选择实现；项目可以登记自己的实现；名字写错时启动失败并列出可选项。
"""

from pathlib import Path

import pytest

from app.setup.backends import Backend, create
from shared.cache.backends import MemoryCache, RedisCache
from shared.errors.framework import ConfigError
from tests.testing_app import make_settings


class OssFiles:
    # 项目自己的文件存储实现（示意），只记下配置的根目录。
    def __init__(self, root: str) -> None:
        self.root = root


# 自带实现按名字创建；项目登记的实现与自带的一样可选；写错名字时列出可选的名字。
def test_choose_backends(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, cache_url="redis://127.0.0.1:6379/0")
    assert isinstance(create("cache", "memory", settings), MemoryCache)
    assert isinstance(create("cache", "redis", settings), RedisCache)
    oss = Backend("files", "oss", "阿里云 OSS", lambda given: OssFiles(given.file_root))
    made = create("files", "oss", settings, [oss])
    assert isinstance(made, OssFiles) and made.root == settings.file_root
    with pytest.raises(ConfigError) as caught:
        create("files", "ftp", settings, [oss])
    assert "可选：local、s3、oss" in str(caught.value)
    with pytest.raises(ConfigError):
        create("files", "local", settings, [Backend("files", "local", "重复", lambda given: None)])
