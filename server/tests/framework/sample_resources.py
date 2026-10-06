"""
测试模块按需请求文件和字段加密服务，不提供任何业务接口或操作。
"""

from shared.public import Module


# 只用于检查文件服务的创建条件。
class FileStore:
    # 接收框架按声明提供的测试资源。
    def __init__(self, files: object) -> None:
        self.files = files


# 只用于检查加密服务的创建条件。
class SecretStore:
    # 接收框架按声明提供的测试资源。
    def __init__(self, vault: object) -> None:
        self.vault = vault


file_module = Module("sample_files", "文件服务测试", "1", provides={}, store=FileStore)
secret_module = Module("sample_secrets", "加密服务测试", "1", provides={}, store=SecretStore)
