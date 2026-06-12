from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Omnicall API", alias="APP_NAME")
    environment: str = Field(default="local", alias="APP_ENV")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    postgres_host: str = Field(default="postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="omnicall", alias="POSTGRES_DB")
    postgres_user: str = Field(default="omnicall", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change-me", alias="POSTGRES_PASSWORD")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: str = Field(default="change-me", alias="REDIS_PASSWORD")
    redis_processing_lock_ttl_seconds: int = Field(default=900, alias="REDIS_PROCESSING_LOCK_TTL_SECONDS")

    rabbitmq_host: str = Field(default="rabbitmq", alias="RABBITMQ_HOST")
    rabbitmq_port: int = Field(default=5672, alias="RABBITMQ_PORT")
    rabbitmq_user: str = Field(default="omnicall", alias="RABBITMQ_USER")
    rabbitmq_password: str = Field(default="change-me", alias="RABBITMQ_PASSWORD")

    minio_host: str = Field(default="minio", alias="MINIO_HOST")
    minio_port: int = Field(default=9000, alias="MINIO_PORT")
    minio_root_user: str = Field(default="omnicall", alias="MINIO_ROOT_USER")
    minio_root_password: str = Field(default="change-me", alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="omnicall-meetings", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    upload_max_bytes: int = Field(default=524288000, alias="UPLOAD_MAX_BYTES")
    upload_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".aac", ".m4a", ".mp3", ".mp4", ".wav", ".webm", ".txt", ".md", ".vtt", ".srt"],
        alias="UPLOAD_ALLOWED_EXTENSIONS",
    )
    upload_allowed_content_types: list[str] = Field(
        default_factory=lambda: [
            "audio/aac",
            "audio/m4a",
            "audio/mpeg",
            "audio/mp4",
            "audio/wav",
            "audio/webm",
            "video/mp4",
            "video/webm",
            "text/plain",
            "text/markdown",
            "text/vtt",
            "application/x-subrip",
        ],
        alias="UPLOAD_ALLOWED_CONTENT_TYPES",
    )

    asr_provider: str = Field(default="local", alias="ASR_PROVIDER")
    speaker_embedding_provider: str = Field(default="wespeaker", alias="SPEAKER_EMBEDDING_PROVIDER")
    analysis_provider: str = Field(default="local", alias="ANALYSIS_PROVIDER")
    text_embedding_provider: str = Field(default="local", alias="TEXT_EMBEDDING_PROVIDER")
    embedding_dimensions: int = Field(default=64, alias="EMBEDDING_DIMENSIONS")
    rerank_provider: str = Field(default="local", alias="RERANK_PROVIDER")
    vector_provider: str = Field(default="milvus", alias="VECTOR_PROVIDER")
    milvus_host: str = Field(default="milvus", alias="MILVUS_HOST")
    milvus_port: int = Field(default=19530, alias="MILVUS_PORT")
    milvus_collection: str = Field(default="meeting_chunks", alias="MILVUS_COLLECTION")

    llm_provider: str = Field(default="endpoint", alias="LLM_PROVIDER")
    llm_api_base_url: str = Field(default="http://localhost:8001/v1", alias="LLM_API_BASE_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_endpoint_compatibility: str = Field(default="openai", alias="LLM_ENDPOINT_COMPATIBILITY")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=1, alias="LLM_MAX_RETRIES")
    llm_retry_backoff_seconds: float = Field(default=0.2, alias="LLM_RETRY_BACKOFF_SECONDS")
    llm_fallback_provider: str = Field(default="ollama", alias="LLM_FALLBACK_PROVIDER")
    ollama_base_url: str = Field(default="http://host.docker.internal:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:3b", alias="OLLAMA_MODEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @computed_field
    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def rabbitmq_url(self) -> str:
        user = quote_plus(self.rabbitmq_user)
        password = quote_plus(self.rabbitmq_password)
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}//"

    @computed_field
    @property
    def redis_url(self) -> str:
        password = quote_plus(self.redis_password)
        return f"redis://:{password}@{self.redis_host}:{self.redis_port}/0"

    @computed_field
    @property
    def minio_endpoint(self) -> str:
        return f"{self.minio_host}:{self.minio_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
