from typing import BinaryIO

from minio import Minio

from backend.configs.settings import Settings, get_settings


class ObjectStorageProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )

    def put_object(
        self,
        *,
        object_key: str,
        data: BinaryIO,
        size_bytes: int,
        content_type: str,
    ) -> None:
        if not self.client.bucket_exists(self.settings.minio_bucket):
            self.client.make_bucket(self.settings.minio_bucket)

        self.client.put_object(
            self.settings.minio_bucket,
            object_key,
            data,
            length=size_bytes,
            content_type=content_type,
        )

    def get_object_bytes(self, *, object_key: str) -> bytes:
        response = self.client.get_object(self.settings.minio_bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def get_object_storage_provider() -> ObjectStorageProvider:
    return ObjectStorageProvider(get_settings())
