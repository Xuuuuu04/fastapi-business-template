from shared.public import Module


class FileStore:
    def __init__(self, files: object) -> None:
        self.files = files


class SecretStore:
    def __init__(self, vault: object) -> None:
        self.vault = vault


file_module = Module("sample_files", "文件服务测试", "1", provides={}, store=FileStore)
secret_module = Module("sample_secrets", "加密服务测试", "1", provides={}, store=SecretStore)
