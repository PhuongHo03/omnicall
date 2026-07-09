from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from backend.configs.settings import Settings, get_settings
from backend.providers.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from backend.utils.exceptions import ApplicationError

_storage_breaker = CircuitBreaker("minio", failure_threshold=5, recovery_seconds=30)


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

        try:
            _storage_breaker.call(
                self.client.put_object,
                self.settings.minio_bucket,
                object_key,
                data,
                length=size_bytes,
                content_type=content_type,
            )
        except CircuitBreakerOpenError as exc:
            raise ApplicationError(503, "service_unavailable", "Object storage is temporarily unavailable.") from exc

    def get_object_bytes(self, *, object_key: str) -> bytes:
        try:
            response = _storage_breaker.call(self.client.get_object, self.settings.minio_bucket, object_key)
        except CircuitBreakerOpenError as exc:
            raise ApplicationError(503, "service_unavailable", "Object storage is temporarily unavailable.") from exc
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def remove_object(self, *, object_key: str) -> None:
        try:
            self.client.remove_object(self.settings.minio_bucket, object_key)
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchBucket"}:
                raise


def get_object_storage_provider() -> ObjectStorageProvider:
    return ObjectStorageProvider(get_settings())
