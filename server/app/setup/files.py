from pathlib import Path

from shared.config.settings import Settings
from shared.errors.framework import ConfigError
from shared.files.storage import FileStorage, LocalFiles, S3Files, S3Options
from shared.files.uploads import UploadArea


def file_components(settings: Settings) -> tuple[FileStorage, UploadArea]:
    uploads = UploadArea(
        Path(settings.upload_root), settings.upload_max_bytes, settings.upload_suffixes
    )
    return file_service(settings), uploads


def file_service(settings: Settings) -> FileStorage:
    if settings.file_storage == "local":
        return LocalFiles(Path(settings.file_root))
    if not settings.s3_bucket:
        raise ConfigError(["APP_FILE_STORAGE=s3 时必须配置 APP_S3_BUCKET"])
    secret = settings.s3_secret_key.get_secret_value() if settings.s3_secret_key else ""
    return S3Files(
        S3Options(
            settings.s3_bucket,
            settings.s3_endpoint,
            settings.s3_region,
            settings.s3_access_key,
            secret,
        )
    )
